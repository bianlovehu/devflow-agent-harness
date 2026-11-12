# 文件用途：用隔离 PostgreSQL 验证真实网关的金额并发、故障、入口共享与只读费用 API。
import io
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
import test_persistence_integration as persistence
from devflow.budget import BudgetLedger
from devflow.config import PROJECT_ROOT, get_settings
from devflow.errors import DomainError
from devflow.fake_model import FixtureModel
from devflow.main import app
from devflow.model_gateway import DeepSeekModel, ModelError, ScriptedModel, Usage, tool_call
from devflow.models import BudgetAccount, MemoryRecord, ModelCharge, RunRecord
from devflow.worker import Worker
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_week05_integration import completed, create_agent_run

pytestmark = persistence.pytestmark
context = persistence.context


def ledger(context):
    return BudgetLedger(context.engine, context.settings)


def reserve(book, **changes):
    return book.reserve(
        **{
            "provider": "aliyun",
            "model": "deepseek-v4.1-flash",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "estimated_input": 120000,
            "output_limit": 20000,
            "purpose": "analysis",
            **changes,
        }
    )


def seed(context, spent):
    with ledger(context).transaction() as session:
        ledger(context).account(session).settled_cny = Decimal(spent)


def real_settings(context):
    return context.settings.model_copy(
        update={
            "model_provider": "aliyun",
            "analysis_executor": "agent",
            "dashscope_api_key": context.settings.deepseek_api_key.__class__("private"),
            "dashscope_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "simulation_step_seconds": 0,
        }
    )


class Opener:
    calls = 0

    def __init__(self, *, bad=False, failure=None, content='{"ok":true}'):
        self.bad, self.failure, self.content = bad, failure, content

    def open(self, request, timeout):
        self.calls += 1
        if self.failure:
            raise self.failure
        return io.BytesIO(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": [] if self.bad else {"content": self.content},
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                }
            ).encode()
        )


def test_budget_read_is_non_mutating_and_settlement_is_exact_idempotent(context):
    book = ledger(context)
    assert book.summary()["settled_cny"] == "0"
    with Session(context.engine) as session:
        assert session.scalar(select(func.count()).select_from(BudgetAccount)) == 0
    run_id = uuid4()  # 外部临时库的运行标识无需在本库创建业务 run。
    receipt = reserve(book, run_id=run_id)
    assert receipt["reserved_cny"] == "0.40000000"
    book.dispatch(receipt["request_id"])
    usage = Usage(prompt_tokens=120000, completion_tokens=20000, total_tokens=140000)
    book.finish(receipt["request_id"], usage)
    book.finish(receipt["request_id"], usage)
    result = BudgetLedger(context.engine, context.settings).snapshot(run_id=run_id)
    assert Decimal(result["settled_cny"]) == Decimal("0.4") and Decimal(result["reserved_cny"]) == 0
    assert len(result["requests"]) == 1


def test_warning_once_and_stop_line_includes_reservations(context):
    book = ledger(context)
    seed(context, "139.6")
    first = reserve(book)
    assert first["warning"]
    book.finish(first["request_id"], sent=False)
    assert not reserve(book)["warning"]
    with book.transaction() as session:
        book.account(session).settled_cny = Decimal("179.2")
    second = reserve(book)  # 179.2 已结算 + 两笔各0.4预留 == 180，允许。
    assert book.summary()["status"] == "blocked"
    with pytest.raises(DomainError) as error:
        reserve(book, estimated_input=1, output_limit=1)
    assert error.value.code == "cost_budget_exceeded"
    book.finish(second["request_id"], sent=False)


def test_concurrent_reservations_cannot_overspend(context):
    seed(context, "179.6")

    def attempt(_):
        try:
            reserve(ledger(context))
            return True
        except DomainError as error:
            assert error.code == "cost_budget_exceeded"
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(4))) == 1
    assert Decimal(ledger(context).summary()["reserved_cny"]) == Decimal("0.4")


def test_expired_unknown_call_keeps_reservation_until_late_usage_arrives(context):
    book = ledger(context)
    receipt = reserve(book)
    book.dispatch(receipt["request_id"])
    with Session(context.engine) as session, session.begin():
        session.get(ModelCharge, UUID(receipt["request_id"])).expires_at = datetime.now(
            UTC
        ) - timedelta(seconds=1)
    assert BudgetLedger(context.engine, context.settings).summary()["unknown_requests"] == 1
    other = reserve(book)
    assert Decimal(book.summary()["reserved_cny"]) == Decimal("0.8")
    book.finish(
        receipt["request_id"],
        Usage(prompt_tokens=100000, completion_tokens=10000, total_tokens=110000),
    )
    assert Decimal(book.summary()["settled_cny"]) == Decimal("0.28")
    book.finish(other["request_id"], sent=False)
    assert Decimal(book.summary()["reserved_cny"]) == 0


@pytest.mark.parametrize("kind", ["ok", "format", "timeout", "cancel"])
def test_gateway_accounts_for_success_format_timeout_and_cancel(context, kind):
    book, opener = (
        ledger(context),
        Opener(bad=kind == "format", failure=TimeoutError() if kind == "timeout" else None),
    )
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if kind == "cancel" and calls == 2:
            raise RuntimeError("cancel before send")

    model = DeepSeekModel(real_settings(context), ledger=book, opener=opener, guard=guard)
    if kind == "ok":
        assert model.complete([], [], max_tokens=1000).request_id
    else:
        with pytest.raises((ModelError, RuntimeError)):
            model.complete([], [], max_tokens=1000)
    value = book.snapshot()
    status = value["requests"][0]["status"]
    assert (
        status
        == {"ok": "settled", "format": "settled", "timeout": "uncertain", "cancel": "released"}[
            kind
        ]
    )
    assert opener.calls == (0 if kind == "cancel" else 1)
    if kind in {"ok", "format"}:
        assert Decimal(value["settled_cny"]) == Decimal("0.00036")


def test_all_model_purposes_and_temporary_analysis_settings_share_primary_ledger(context):
    book, opener = ledger(context), Opener()
    with patch("devflow.model_gateway.get_budget_ledger", return_value=book):
        for purpose in ["analysis", "memory", "probe"]:
            settings = real_settings(context).model_copy(
                update={"postgres_db": "temporary_analysis_database"}
            )
            DeepSeekModel(
                settings, opener=opener, purpose=purpose, run_id=uuid4(), source="isolated_smoke"
            ).complete([], [], max_tokens=1000)
    values = book.snapshot()
    assert {v["purpose"] for v in values["requests"]} == {"analysis", "memory", "probe"}
    assert Decimal(values["settled_cny"]) == Decimal("0.00108")


def test_blocked_worker_and_memory_extraction_preserve_reports_and_do_not_send(context):
    previous = completed(context)
    seed(context, "180")
    settings = real_settings(context)
    app.dependency_overrides[get_settings] = lambda: settings
    body = persistence.create_target(context)
    run = context.client.post("/api/v1/runs", json={**body, "use_knowledge": False}).json()
    worker = Worker(context.engine, settings, context.store, budget_ledger=ledger(context))
    worker.execute(*worker.claim(UUID(run["id"])))
    result = context.client.get(f"/api/v1/runs/{run['id']}").json()
    assert result["status"] == "needs_attention" and result["error_code"] == "cost_budget_exceeded"
    events = context.client.get(f"/api/v1/runs/{run['id']}/events").json()["items"]
    assert any(e["event_type"] == "budget.blocked" for e in events)
    blocked = context.client.post(
        f"/api/v1/runs/{previous['id']}/memories", json={"finding_index": 0}
    )
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "cost_budget_exceeded"
    with Session(context.engine) as session:
        assert session.scalar(select(func.count()).select_from(MemoryRecord)) == 0
        assert session.scalar(select(func.count()).select_from(ModelCharge)) == 0
    assert context.client.get(f"/api/v1/runs/{previous['id']}/report").status_code == 200


def test_looping_worker_needs_attention_and_cost_api_marks_old_runs(context):
    run, worker = create_agent_run(context)
    worker.model_factory = lambda _: ScriptedModel(
        [tool_call("get_pr", {"repo_id": "repo-taskboard"}, str(i)) for i in range(4)]
    )
    worker.execute(*worker.claim(UUID(run["id"])))
    assert context.client.get(f"/api/v1/runs/{run['id']}").json()["error_code"] == "loop_detected"
    cost = context.client.get(f"/api/v1/runs/{run['id']}/cost").json()
    assert cost["tracked"] and not cost["requests"]
    with Session(context.engine) as session, session.begin():
        record = session.get(RunRecord, UUID(run["id"]))
        record.configuration = {
            k: v for k, v in record.configuration.items() if k != "runtime_policy_version"
        }
    assert not context.client.get(f"/api/v1/runs/{run['id']}/cost").json()["tracked"]
    assert context.client.get("/api/v1/budget").json()["limits"]["input_tokens"] == 120000


def test_worker_process_crash_retains_cost_reservation_after_recovery(context):
    settings = real_settings(context)
    app.dependency_overrides[get_settings] = lambda: settings
    body = persistence.create_target(context)
    run = context.client.post("/api/v1/runs", json={**body, "use_knowledge": False}).json()
    child = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("budget_crash_worker.py")),
            context.database_name,
            str(context.store.root),
            run["id"],
        ],
        cwd=PROJECT_ROOT,
        timeout=40,
        capture_output=True,
    )
    assert child.returncode == 73, child.stderr.decode(errors="replace")
    book = BudgetLedger(context.engine, settings)
    amount = Decimal(book.summary()["reserved_cny"])
    assert amount > 0
    with Session(context.engine) as session, session.begin():
        session.get(RunRecord, UUID(run["id"])).lease_expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        charge = session.scalar(select(ModelCharge))
        charge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    worker = Worker(context.engine, settings, context.store, model_factory=lambda _: FixtureModel())
    worker.execute(*worker.claim(UUID(run["id"])))
    result = context.client.get(f"/api/v1/runs/{run['id']}").json()
    assert result["status"] == "succeeded" and result["recovery_count"] == 1
    assert result["result"]["unknown_usage_calls"] == 1
    assert Decimal(book.summary()["reserved_cny"]) == amount
    assert book.summary()["unknown_requests"] == 1


def test_missing_price_or_ledger_failure_prevents_any_http_request(context):
    opener = Opener()
    settings = real_settings(context).model_copy(update={"dashscope_model": "unpriced-model"})
    with pytest.raises(DomainError) as error:
        DeepSeekModel(settings, ledger=ledger(context), opener=opener).complete([], [])
    assert error.value.code == "pricing_not_configured" and opener.calls == 0
    book = ledger(context)
    with patch.object(
        context.engine, "connect", side_effect=OperationalError("private", {}, Exception())
    ):
        with pytest.raises(DomainError) as error:
            DeepSeekModel(real_settings(context), ledger=book, opener=opener).complete([], [])
    assert error.value.code == "budget_unavailable" and opener.calls == 0


def test_actual_usage_above_reservation_is_recorded_and_next_request_is_blocked(context):
    seed(context, "179.99")
    book = ledger(context)
    receipt = reserve(book, estimated_input=1, output_limit=1)
    book.dispatch(receipt["request_id"])
    book.finish(
        receipt["request_id"],
        Usage(prompt_tokens=100000, completion_tokens=20000, total_tokens=120000),
    )
    assert Decimal(book.summary()["settled_cny"]) == Decimal("180.35")
    with pytest.raises(DomainError) as error:
        reserve(book)
    assert error.value.code == "cost_budget_exceeded"


def test_actual_usage_crossing_warning_line_notifies_once(context):
    seed(context, "139.9998")
    notifications = []
    model = DeepSeekModel(
        real_settings(context),
        ledger=ledger(context),
        opener=Opener(),
        emit=lambda name, payload: notifications.append(name),
    )
    reply = model.complete([], [], max_tokens=1)
    assert Decimal(ledger(context).summary()["settled_cny"]) == Decimal("140.00016")
    assert notifications == ["budget.warning"]
    assert ledger(context).finish(reply.request_id, reply.usage) is None
