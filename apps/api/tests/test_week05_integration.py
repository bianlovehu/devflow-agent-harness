# 文件用途：以隔离真实数据库和强制退出的子进程验证审核、恢复、预算留痕与安全边界。
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
import test_persistence_integration as persistence
from devflow.config import PROJECT_ROOT
from devflow.memory import recall_memories
from devflow.models import MemoryRecord, MessageRecord, ResourceSnapshot, RunRecord
from devflow.worker import LeaseLost, Worker
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = persistence.pytestmark
context = persistence.context


def create_agent_run(context, **changes):
    body = {**persistence.create_target(context), "use_knowledge": False, **changes}
    settings = context.settings.model_copy(
        update={"analysis_executor": "agent", "simulation_step_seconds": 0}
    )
    from devflow.config import get_settings
    from devflow.main import app

    app.dependency_overrides[get_settings] = lambda: settings
    result = context.client.post("/api/v1/runs", json=body)
    assert result.status_code == 201, result.text
    return result.json(), Worker(context.engine, settings, context.store)


def completed(context):
    run, worker = create_agent_run(context)
    worker.execute(*worker.claim(UUID(run["id"])))
    result = context.client.get(f"/api/v1/runs/{run['id']}").json()
    assert result["status"] == "succeeded", result
    return result


def candidate(context, run, index=0):
    result = context.client.post(
        f"/api/v1/runs/{run['id']}/memories", json={"finding_index": index}
    )
    assert result.status_code == 201, result.text
    return result.json()


def mutate(context, memory, action, data=None, repo="repo-taskboard"):
    if action == "approve":
        indexed = context.client.post(
            f"/api/v1/memories/{memory['id']}/index?repo_id={repo}", json={}
        )
        assert indexed.status_code == 200, indexed.text
        data = {
            **(data or {}),
            "reviewed_conflicts": {
                c["id"]: c["content_revision"] for c in indexed.json()["conflicts"]
            },
        }
    result = context.client.post(
        f"/api/v1/memories/{memory['id']}/{action}?repo_id={repo}", json=data or {}
    )
    assert result.status_code == 200, result.text
    return result.json()


def recalled(context, version):
    with Session(context.engine) as session:
        return recall_memories(session, "repo-taskboard", version)


def test_memory_approval_version_expiry_revoke_edit_and_restart(context):
    run = completed(context)
    memory = candidate(context, run)
    version = run["input_version"]["resources"][0]["head_sha"]
    assert memory["status"] == "pending" and memory["applicable_version"] == version
    assert not recalled(context, version)
    assert candidate(context, run)["id"] == memory["id"]
    mutate(context, memory, "approve")
    assert [m["id"] for m in recalled(context, version)] == [memory["id"]]
    assert not recalled(context, "f" * 40)
    context.engine.dispose()  # 新连接池/会话不依赖任何进程内记忆。
    assert recalled(context, version)
    next_run, worker = create_agent_run(context)
    worker.execute(*worker.claim(UUID(next_run["id"])))
    result = context.client.get(f"/api/v1/runs/{next_run['id']}").json()
    assert result["result"]["recalled_memories"] == [memory["id"]]
    mutate(
        context,
        memory,
        "edit",
        {"summary": "人工修订：需验证所有者隔离", "applicable_version": None},
    )
    assert not recalled(context, version)
    mutate(context, memory, "approve")
    assert recalled(context, "f" * 40)  # 经人工审核允许仓库通用。
    mutate(context, memory, "revoke")
    assert not recalled(context, version)
    assert (
        context.client.post(
            f"/api/v1/memories/{memory['id']}/approve?repo_id=repo-taskboard", json={}
        ).status_code
        == 409
    )


def test_replacement_expiry_and_repository_isolation(context):
    run = completed(context)
    old = candidate(context, run)
    mutate(context, old, "approve")
    newer = candidate(context, completed(context))
    mutate(context, newer, "approve", {"replaces_id": old["id"]})
    with Session(context.engine) as session, session.begin():
        assert session.get(MemoryRecord, UUID(old["id"])).status == "superseded"
        record = session.get(MemoryRecord, UUID(newer["id"]))
        record.created_at = datetime.now(UTC) - timedelta(days=32)
        record.expires_at = datetime.now(UTC) - timedelta(days=1)
    assert not recalled(context, newer["applicable_version"])
    listing = context.client.get("/api/v1/memories?repo_id=repo-taskboard").json()["items"]
    assert next(m for m in listing if m["id"] == newer["id"])["expired"]
    response = context.client.post(f"/api/v1/memories/{old['id']}/revoke?repo_id=other", json={})
    assert response.status_code == 404


@pytest.mark.parametrize("point", ["after_tool", "model_call", "before_report"])
def test_real_process_crash_resumes_fixed_snapshot_without_duplicate_business_writes(
    context, point
):
    run, worker = create_agent_run(context)
    run_id = UUID(run["id"])
    child = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("crash_worker.py")),
            context.database_name,
            str(context.store.root),
            run["id"],
            point,
        ],
        cwd=PROJECT_ROOT,
        timeout=40,
        capture_output=True,
    )
    assert child.returncode == 73, child.stderr.decode(errors="replace")
    crashed = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert crashed["status"] == "running"
    before = context.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    original_token = None
    with Session(context.engine) as session, session.begin():
        record = session.get(RunRecord, run_id)
        original_token = record.lease_token
        record.lease_expires_at = session.scalar(select(func.clock_timestamp())) - timedelta(
            seconds=1
        )
    # 新 worker 自动 reaper -> claim -> 从 PostgreSQL checkpoint / 已完成工具 journal 恢复。
    claimed = worker.claim(run_id)
    assert claimed and claimed[1] != original_token
    with pytest.raises(LeaseLost):
        worker._journal_write(run_id, original_token, "stale-write", {})
    worker.execute(*claimed)
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "succeeded", result
    assert result["recovery_count"] == 1 and result["attempt"] == 2
    assert result["input_version"] == run["input_version"]
    assert result["result"]["report"]["findings"]
    after = context.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    assert sum(e["event_type"] == "run.succeeded" for e in after) == 1
    assert after[: len(before)] == before
    agent_tools = [
        e
        for e in after
        if e["event_type"] == "tool.completed"
        and e["payload"].get("tool") not in {"verify_artifacts", "capture_github"}
    ]
    assert len(agent_tools) == result["result"]["tool_calls"]
    with Session(context.engine) as session:
        messages = session.scalars(
            select(MessageRecord).where(
                MessageRecord.conversation_id == UUID(run["conversation_id"]),
                MessageRecord.role == "assistant",
            )
        ).all()
        assert len(messages) == 1
        assert (
            session.execute(
                text("SELECT count(*) FROM devflow_checkpoints.checkpoints WHERE thread_id=:id"),
                {"id": str(run_id)},
            ).scalar()
            > 0
        )
    if point == "model_call":
        assert result["result"]["unknown_usage_calls"] == 1
        assert result["result"]["recovery_model_calls"] >= 1


def test_second_worker_loss_stops_and_missing_artifacts_do_not_recapture(context):
    run, worker = create_agent_run(context)
    run_id = UUID(run["id"])
    first = worker.claim(run_id)
    for attempt in range(2):
        with Session(context.engine) as session, session.begin():
            session.get(RunRecord, run_id).lease_expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )
        if attempt == 0:
            assert worker.claim(run_id)
        else:
            assert worker.claim(run_id) is None
    assert context.client.get(f"/api/v1/runs/{run_id}").json()["status"] == "needs_attention"
    with pytest.raises(LeaseLost):
        worker._finish(*first, "succeeded")


def test_context_material_usage_error_and_stale_report_are_reviewable(context):
    run = completed(context)
    endpoint = f"/api/v1/runs/{run['id']}"
    calls = context.client.get(endpoint + "/context").json()["calls"]
    assert calls and all(call["context"]["estimated_input"] <= 12000 for call in calls)
    detail = context.client.get(endpoint + "/context?call=1").json()["calls"][0]
    assert detail["original_request"] and detail["request"]
    assert "estimation_error" in detail["context"]
    assert not context.client.get(endpoint + "/freshness").json()["stale"]
    with Session(context.engine) as session, session.begin():
        snapshot = session.get(
            ResourceSnapshot, UUID(run["input_version"]["resources"][0]["snapshot_id"])
        )
        snapshot.payload = {**snapshot.payload, "head_sha": "f" * 40}
    assert context.client.get(endpoint + "/freshness").json()["stale"]
    assert context.client.get(endpoint + "/report").status_code == 200


def test_long_conversation_runs_with_constraints_and_original_material(context):
    # 验证小预算下的压缩行为；新默认预算已提升到120,000。
    context.settings = context.settings.model_copy(update={"context_input_tokens": 12000})
    run, worker = create_agent_run(context)
    conversation = run["conversation_id"]
    response = context.client.post(
        f"/api/v1/conversations/{conversation}/messages",
        json={"content": "重复历史背景 " * 2400 + "。必须核查 owner_id。尚未解决 null 标签。"},
    )
    assert response.status_code == 201
    next_run, worker = create_agent_run(context, conversation_id=conversation)
    worker.execute(*worker.claim(UUID(next_run["id"])))
    endpoint = f"/api/v1/runs/{next_run['id']}"
    assert context.client.get(endpoint).json()["status"] == "succeeded"
    detail = context.client.get(endpoint + "/context?call=1").json()["calls"][0]
    assert detail["context"]["saved_tokens"] > 10000
    assert "必须核查 owner_id" in json.dumps(detail["request"], ensure_ascii=False)
    assert len(json.dumps(detail["original_request"])) > len(json.dumps(detail["request"]))


def test_missing_snapshot_artifact_on_recovery_fails_without_fresh_capture(context):
    run, worker = create_agent_run(context)
    run_id = UUID(run["id"])
    worker.claim(run_id)
    from devflow.workflows import run_artifacts

    with Session(context.engine) as session, session.begin():
        artifacts = run_artifacts(session, run_id)
        (context.store.root / artifacts[0].storage_key).unlink()
        session.get(RunRecord, run_id).lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    worker.execute(*worker.claim(run_id))
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "needs_attention" and result["error_code"] == "artifact_missing"
    assert result["input_version"] == run["input_version"]


def test_revoked_memory_disappears_before_next_model_request(context):
    run = completed(context)
    memory = candidate(context, run)
    mutate(context, memory, "approve")
    from devflow.fake_model import FixtureModel

    class RevokingModel(FixtureModel):
        def __init__(self):
            self.requests = []

        def complete(self, messages, tools, **kwargs):
            self.requests.append(messages)
            if len(self.requests) == 1:
                mutate(context, memory, "revoke")
            return super().complete(messages, tools, **kwargs)

    model = RevokingModel()
    next_run, worker = create_agent_run(context)
    worker.model_factory = lambda _: model
    worker.execute(*worker.claim(UUID(next_run["id"])))
    assert memory["id"] in json.dumps(model.requests[0])
    assert memory["id"] not in json.dumps(model.requests[1])
    assert context.client.get(f"/api/v1/runs/{next_run['id']}").json()["status"] == "succeeded"


def test_api_and_model_inputs_redact_secrets_but_preserve_original_artifacts(context):
    from devflow.models import ArtifactRecord

    secret = "ghp_" + "a" * 36
    run, worker = create_agent_run(context, question="请审查；不可信资料中包含令牌 " + secret)
    worker.execute(*worker.claim(UUID(run["id"])))
    endpoint = f"/api/v1/runs/{run['id']}/context?call=1"
    response = context.client.get(endpoint)
    assert response.status_code == 200 and secret not in response.text
    assert "[REDACTED]" in response.text
    key, digest, size = context.store.put_text("first\n" + secret + "\nlast\n")
    with Session(context.engine, expire_on_commit=False) as session, session.begin():
        artifact = ArtifactRecord(
            repo_id="repo-taskboard",
            storage_key=key,
            sha256=digest,
            size_bytes=size,
            media_type="text/plain",
        )
        session.add(artifact)
        session.flush()
        artifact_id = artifact.id
    content = context.client.get(f"/api/v1/artifacts/{artifact_id}?repo_id=repo-taskboard").json()[
        "content"
    ]
    assert secret not in content and content.splitlines() == ["first", "[REDACTED]", "last"]
    assert secret in context.store.read_text(key, digest)
