# 文件用途：在同一份初稿上对比复核前后，逐题保存真实用量、费用和补查轨迹。
import argparse
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from devflow.agent import model_configuration
from devflow.budget import get_budget_ledger
from devflow.config import PROJECT_ROOT, get_settings
from devflow.eval_cli import provenance
from devflow.eval_retrieval import ProductionRetrieval
from devflow.eval_runner import execute_case
from devflow.evaluation import digest, grade, load_dataset, read_json, write_json
from devflow.models import ModelCharge
from devflow.runtime_policy import cost


def initial_execution(execution, quote):
    result = execution.get("result") or {}
    record = result.get("report_review") or execution.get("report_review_state")
    if not record:
        return deepcopy(execution)
    before = deepcopy(execution)
    before.pop("report_review_state", None)
    if not before.get("result"):
        configuration = before["trace"]["configuration"]
        before["result"] = {
            "kind": "analysis_report",
            "provider": configuration["provider"],
            "model": configuration["model"],
        }
    before["error"] = None
    before["result"].pop("report_review", None)
    before["result"]["report"] = record["initial_report"]
    before["usage"] = record["initial_usage"]
    before["result"]["usage"] = record["initial_usage"]
    before["duration_ms"] = record["initial_duration_ms"]
    before["observed"] = record["initial_observed"]
    initial_ids = {r["evidence_id"] for r in record["initial_report"]["evidence_facts"]["reads"]}
    before["evidence"] = [e for e in before["evidence"] if e["id"] in initial_ids]
    before["result"]["tool_calls"] = record.get("initial_tool_calls")
    before["trace"]["calls"] = [
        c for c in before["trace"]["calls"] if c.get("phase", "analysis") == "analysis"
    ]
    before["result"]["model_calls"] = len(before["trace"]["calls"])
    before["usage_unknown"] = any("usage" not in c for c in before["trace"]["calls"])
    before["known_usage_cost_cny"] = (
        str(cost(before["usage"]["prompt_tokens"], before["usage"]["completion_tokens"], quote))
        if quote
        else None
    )
    return before


def run_batch(args):
    settings = get_settings()
    if settings.model_provider == "fake":
        raise ValueError("真实对比不能使用离线模拟模型")
    cases, labels, dataset = load_dataset(args.dataset)
    cases = [c for c in cases if c.split == "dev"]
    if args.case:
        chosen = set(args.case)
        if chosen - {c.case_id for c in cases}:
            raise ValueError("只允许选择已有开发题")
        cases = [c for c in cases if c.case_id in chosen]
    configuration = model_configuration(settings)
    origin = provenance()
    fingerprint = digest(
        {
            "dataset": dataset,
            "cases": [c.case_id for c in cases],
            "configuration": configuration,
            "provenance": origin["working_code_sha256"],
        }
    )
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "state.json"
    ledger = get_budget_ledger()
    before = ledger.summary()
    if state_path.exists():
        state = read_json(state_path)
        if state["fingerprint"] != fingerprint:
            raise ValueError("代码、配置或输入已改变，请使用新目录，不覆盖原结果")
    else:
        state = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "batch_id": uuid4().hex,
            "fingerprint": fingerprint,
            "configuration": configuration,
            "provenance": origin,
            "dataset": dataset,
            "cases": [c.case_id for c in cases],
            "completed": [],
            "budget_initial": before,
            "batches": [],
            "corpus_instances": [],
            "comparison": "同一次真实分析的原始初稿与复核后报告；不是两次不同生成结果的对比",
            "blind": False,
            "quality_status": "pending_gpt_review",
        }
        write_json(state_path, state)
        write_json(
            directory / "source-snapshot.json",
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "provenance": origin,
                "files": {
                    str(p.relative_to(PROJECT_ROOT)): p.read_text(encoding="utf-8")
                    for p in sorted((PROJECT_ROOT / "apps/api/src/devflow").glob("*.py"))
                },
            },
        )
    pending = [c for c in cases if c.case_id not in state["completed"]][: args.limit]
    if not pending:
        print("所有计划题目已完成。", flush=True)
        return 0
    if before["status"] == "blocked":
        raise ValueError("原共享账本已到停止线，未发送请求")
    (directory / "jobs").mkdir(exist_ok=True)
    with ProductionRetrieval(settings, cases, directory / "artifacts") as corpus:
        state["corpus_instances"].append(corpus.manifest)
        write_json(state_path, state)
        for case in pending:
            current = ledger.summary()
            spent = (
                Decimal(current["settled_cny"])
                + Decimal(current["reserved_cny"])
                - Decimal(before["settled_cny"])
                - Decimal(before["reserved_cny"])
            )
            if current["status"] == "blocked" or spent >= Decimal(args.batch_cap_cny):
                break
            source = f"eval:{state['batch_id']}:{digest(case.case_id)[:16]}"
            print({"case": case.case_id, "available_cny": current["available_cny"]}, flush=True)
            execution = execute_case(
                case, settings, knowledge_search=corpus.tool(case, "hybrid"), charge_source=source
            )
            original = initial_execution(execution, configuration["pricing_snapshot"])
            with Session(ledger.engine) as session:
                billing = [
                    {
                        "id": str(c.id),
                        "status": c.status,
                        "reserved_cny": str(c.reserved_cny),
                        "settled_cny": str(c.settled_cny) if c.settled_cny is not None else None,
                        "usage": c.usage,
                        "pricing": c.pricing,
                    }
                    for c in session.scalars(
                        select(ModelCharge).where(ModelCharge.source == source)
                    ).all()
                ]
            row = {
                "case_id": case.case_id,
                "case_sha256": digest(case.model_dump()),
                "expectation": labels[case.case_id].model_dump(),
                "before": original,
                "after": execution,
                "before_sha256": digest(original),
                "after_sha256": digest(execution),
                "before_automatic_checks": grade(case, labels[case.case_id], original),
                "after_automatic_checks": grade(case, labels[case.case_id], execution),
                "corpus_sha256": corpus.manifest["corpus_sha256"],
                "billing": billing,
                "gpt_review": {"status": "pending"},
            }
            target = directory / "jobs" / (case.case_id + ".json")
            if target.exists():
                raise ValueError("已有结果文件，拒绝覆盖")
            write_json(target, row)
            state["completed"].append(case.case_id)
            state["budget_latest"] = ledger.summary()
            write_json(state_path, state)
            write_json(directory / "retrieval-queries.json", corpus.queries)
            print(
                {
                    "completed": case.case_id,
                    "before_error": original["error"],
                    "after_error": execution["error"],
                    "usage": execution["usage"],
                    "cost_cny": execution["known_usage_cost_cny"],
                    "review_status": (execution.get("result") or {})
                    .get("report_review", {})
                    .get("status"),
                },
                flush=True,
            )
            codes = {c.get("error_code") for c in execution["trace"]["calls"]}
            if codes & {
                "model_auth_error",
                "model_balance_error",
                "model_network_error",
                "model_rate_limited",
                "cost_budget_exceeded",
                "budget_unavailable",
                "pricing_not_configured",
            }:
                state["stop_reason"] = sorted(str(c) for c in codes if c)
                break
    state["batches"].append({"before": before, "after": ledger.summary()})
    write_json(state_path, state)
    return 1 if state.get("stop_reason") else 0


def main():
    parser = argparse.ArgumentParser(description="限次复核的真实开发题对比，沿用原共享账本")
    parser.add_argument("--real", action="store_true", required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--dataset", default=str(PROJECT_ROOT / "evals/devflow-v1"))
    parser.add_argument("--case", action="append")
    parser.add_argument("--limit", type=int, choices=range(1, 7), default=3)
    parser.add_argument("--batch-cap-cny", default="5")
    args = parser.parse_args()
    if Decimal(args.batch_cap_cny) > 5 or Decimal(args.batch_cap_cny) <= 0:
        parser.error("每批费用上限只能为0到5元")
    return run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
