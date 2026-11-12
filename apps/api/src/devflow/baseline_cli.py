# 文件用途：分批运行真实开发集、检索/压缩对照和重复采样；逐题落盘，主库共享账本不重置。
import argparse
import json
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

REPRESENTATIVE_CASES = ["pr-owner-removed", "ci-lint", "qa-owner"]


def plan_jobs(cases, suite):
    selected = (
        cases if suite == "analysis" else [c for c in cases if c.case_id in REPRESENTATIVE_CASES]
    )
    jobs = []
    for case in selected:
        arms = (
            ["keyword", "hybrid"]
            if suite == "analysis"
            else ["uncompressed", "budgeted"]
            if suite == "context"
            else ["hybrid"]
        )
        for arm in arms:
            for repeat in range(1, 4 if suite == "stability" else 2):
                jobs.append(
                    {
                        "job_id": f"{case.case_id}-{arm}-{repeat}",
                        "case_id": case.case_id,
                        "arm": arm,
                        "repeat": repeat,
                    }
                )
    return jobs


def run_batch(args):
    settings = get_settings()
    if settings.model_provider == "fake":
        raise ValueError("真实基线拒绝fake供应商；请保留独立fake工程回归")
    cases, labels, dataset = load_dataset(args.dataset)
    # 旧holdout已被查看；本命令默认只开发集。新集须提供冻结文件并显式选择holdout。
    if args.split == "holdout" and not args.freeze:
        raise ValueError("新留出评测必须先提供开发冻结记录 --freeze")
    cases = [c for c in cases if c.split == args.split]
    if not cases:
        raise ValueError("所选集为空")
    configuration = model_configuration(settings)
    origin = provenance()
    if args.freeze:
        freeze = read_json(args.freeze)
        if freeze["working_code_sha256"] != origin["working_code_sha256"]:
            raise ValueError("开发冻结后执行代码已变化，不允许混用留出成绩")
    ledger = get_budget_ledger()
    before = ledger.summary()
    if before["status"] == "blocked":
        raise ValueError("主库预算已停止，不能开始新批次")
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    state_file = directory / "state.json"
    fingerprint = digest(
        {
            "dataset": dataset,
            "configuration": configuration,
            "code": origin["working_code_sha256"],
            "suite": args.suite,
            "split": args.split,
        }
    )
    if state_file.exists():
        state = read_json(state_file)
        if state["fingerprint"] != fingerprint:
            raise ValueError("配置/代码/数据变化，请使用新目录保留原始基线")
    else:
        state = {
            "schema_version": 1,
            "batch_id": uuid4().hex,
            "fingerprint": fingerprint,
            "created_at": datetime.now(UTC).isoformat(),
            "suite": args.suite,
            "dataset": dataset,
            "configuration": configuration,
            "provenance": origin,
            "budget_initial": before,
            "budget_batches": [],
            "jobs": plan_jobs(cases, args.suite),
            "completed": [],
            "corpus_instances": [],
            "old_holdout_exposure": "seen; regression only",
        }
        write_json(state_file, state)
    pending = [j for j in state["jobs"] if j["job_id"] not in state["completed"]][: args.limit]
    if not pending:
        print("All scheduled jobs are complete.")
        return 0
    case_map = {c.case_id: c for c in cases}
    # 每批最多几题；每一次真实请求仍通过原账本原子预留和结算，不另建预算账户。
    with ProductionRetrieval(settings, cases, directory / "artifacts") as corpus:
        state["corpus_instances"].append(corpus.manifest)
        if not (directory / "retrieval.json").exists():
            write_json(
                directory / "retrieval.json",
                {"corpus": corpus.manifest, "rows": corpus.evaluate(cases)},
            )
        for job in pending:
            current = ledger.summary()
            delta = (
                Decimal(current["settled_cny"])
                + Decimal(current["reserved_cny"])
                - Decimal(before["settled_cny"])
                - Decimal(before["reserved_cny"])
            )
            if current["status"] == "blocked" or delta >= Decimal(args.batch_cap_cny):
                print("Batch spending cap reached; no new request sent.")
                break
            case = case_map[job["case_id"]]
            mode = job["arm"] if job["arm"] in {"keyword", "hybrid"} else "hybrid"
            updates, history = {}, []
            if args.suite == "context":
                updates = {
                    "context_mode": job["arm"],
                    "context_input_tokens": 120000 if job["arm"] == "uncompressed" else 20000,
                }
                # 两臂使用完全相同的固定会话历史；仅压缩策略/目标预算不同。
                history = [
                    {
                        "id": f"history-{index}",
                        "role": "user",
                        "content": "历史讨论（不代表当前事实）："
                        + "请区分历史资料与当前提交，保留证据版本和未确认事项。" * 35,
                    }
                    for index in range(12)
                ]
            source = f"eval:{state['batch_id']}:{digest(job['job_id'])[:16]}"
            print(
                json.dumps(
                    {
                        "job": job["job_id"],
                        "provider": settings.model_provider,
                        "budget_available_cny": current["available_cny"],
                    }
                ),
                flush=True,
            )
            execution = execute_case(
                case,
                settings,
                knowledge_search=corpus.tool(case, mode),
                configuration_updates=updates,
                history=history,
                charge_source=source,
            )
            with Session(ledger.engine) as session:
                charges = session.scalars(
                    select(ModelCharge).where(ModelCharge.source == source)
                ).all()
                billing = [
                    {
                        "id": str(c.id),
                        "status": c.status,
                        "reserved_cny": str(c.reserved_cny),
                        "settled_cny": str(c.settled_cny) if c.settled_cny is not None else None,
                        "usage": c.usage,
                        "pricing": c.pricing,
                    }
                    for c in charges
                ]
            row = {
                **job,
                "case_sha256": digest(case.model_dump()),
                "expectation": labels[case.case_id].model_dump(),
                "execution": execution,
                "automatic_checks": grade(case, labels[case.case_id], execution),
                "review": {"verdict": "pending"},
                "billing": billing,
                "retrieval_mode": mode,
                "corpus_sha256": corpus.manifest["corpus_sha256"],
                "failure_attribution": (
                    "automatic proxies require semantic review; "
                    "check retrieval/read/schema separately"
                ),
            }
            jobs_dir = directory / "jobs"
            jobs_dir.mkdir(exist_ok=True)
            write_json(jobs_dir / (job["job_id"] + ".json"), row)
            state["completed"].append(job["job_id"])
            state["budget_latest"] = ledger.summary()
            write_json(state_file, state)
            write_json(directory / "retrieval-queries.json", corpus.queries)
            print(
                json.dumps(
                    {
                        "completed": job["job_id"],
                        "error": execution["error"],
                        "usage": execution["usage"],
                        "charges": billing,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            error_code = (execution.get("error") or {}).get("code")
            if error_code in {
                "model_auth_error",
                "model_configuration_error",
                "pricing_not_configured",
                "cost_budget_exceeded",
                "budget_unavailable",
                "model_balance_error",
                "model_network_error",
                "model_rate_limited",
            }:
                state["stop_reason"] = error_code
                break
    state["budget_batches"].append({"before": before, "after": ledger.summary()})
    state["remaining_jobs"] = len(state["jobs"]) - len(state["completed"])
    write_json(state_file, state)
    print(
        f"Saved {len(state['completed'])}/{len(state['jobs'])} jobs; "
        "isolated corpus database removed."
    )
    return 1 if state.get("stop_reason") else 0


def main():
    parser = argparse.ArgumentParser(description="真实模型与生产检索分层基线（显式付费调用）")
    parser.add_argument("--real", action="store_true", required=True)
    parser.add_argument("--dataset", default=str(PROJECT_ROOT / "evals/devflow-v1"))
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--suite", choices=["analysis", "context", "stability"], default="analysis")
    parser.add_argument("--directory", required=True)
    parser.add_argument("--limit", type=int, choices=range(1, 7), default=3)
    parser.add_argument("--batch-cap-cny", default="5")
    parser.add_argument("--freeze")
    args = parser.parse_args()
    if Decimal(args.batch_cap_cny) <= 0:
        parser.error("批次费用上限必须大于0")
    try:
        return run_batch(args)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
