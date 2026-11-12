# 文件用途：统一评测、失败重跑、人工复核和回归比较入口，默认不调用真实模型。
import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from devflow.config import PROJECT_ROOT, Settings, get_settings
from devflow.eval_runner import RETRIEVAL_PROFILE, evaluation_configuration, execute_case
from devflow.evaluation import (
    EVALUATOR_VERSION,
    aggregate,
    apply_reviews,
    compare_runs,
    digest,
    grade,
    load_dataset,
    quality_exit,
    read_json,
    review_template,
    save_run,
    write_json,
)


def result_file(value):
    path = Path(value)
    return path / "results.json" if path.is_dir() else path


def new_directory(value):
    path = Path(value)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("输出目录必须不存在或为空，避免覆盖历史证据")
    return path


def provenance():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT, text=True).strip()

    paths = [
        *sorted((PROJECT_ROOT / "apps/api/src/devflow").glob("*.py")),
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / "uv.lock",
    ]
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "working_code_sha256": digest(
            {str(p.relative_to(PROJECT_ROOT)): digest(p.read_text(encoding="utf-8")) for p in paths}
        ),
    }


def run_command(args):
    cases, labels, dataset = load_dataset(args.dataset)
    if args.case and args.cases_from:
        raise ValueError("--case 与 --cases-from 不能同时使用")
    selected = set(args.case or [])
    if args.cases_from:
        failures = read_json(args.cases_from)
        if failures["dataset"] != dataset:
            raise ValueError("失败列表属于其他数据集")
        selected = set(failures["case_ids"])
        if not selected:
            raise ValueError("没有失败案例可重跑")
    allowed = [c for c in cases if args.split == "all" or c.split == args.split]
    if selected - {c.case_id for c in allowed}:
        raise ValueError("指定案例不存在或不在所选 split 中")
    cases = [c for c in allowed if not selected or c.case_id in selected]
    if not cases:
        raise ValueError("评测集为空")
    # fake 显式忽略 .env 内的供应商与密钥；真实调用必须选择 configured。
    settings = (
        Settings(_env_file=None, model_provider="fake")
        if args.provider == "fake"
        else get_settings()
    )
    config = evaluation_configuration(settings)
    profile = {
        "provider": settings.model_provider,
        "model": "fixture-demo-v1" if settings.model_provider == "fake" else config["model"],
        "retrieval": RETRIEVAL_PROFILE,
    }
    run = {
        "schema_version": 1,
        "evaluator_version": EVALUATOR_VERSION,
        "run_id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": dataset,
        "split": args.split,
        "profile": profile,
        "configuration": config,
        "provenance": provenance(),
        "cases": [],
    }
    for case in cases:
        row = {
            "case_id": case.case_id,
            "task_type": case.task_type,
            "split": case.split,
            "source_group": case.source_group,
            "case_sha256": digest(
                {"input": case.model_dump(), "expected": labels[case.case_id].model_dump()}
            ),
            "expectation": labels[case.case_id].model_dump(),
            "failures": [],
            "review": {"verdict": "pending"},
        }
        run["cases"].append(row)
    run["summary"] = {"review_pending": len(cases)}
    baseline = read_json(result_file(args.baseline)) if args.baseline else None
    if baseline:
        compare_runs(baseline, run)  # 不兼容的基线在调用模型前拒绝。
    output = new_directory(args.output or PROJECT_ROOT / "data/evals" / run["run_id"])
    for case, row in zip(cases, run["cases"], strict=True):
        row["execution"] = execute_case(case, settings)
        row["failures"] = grade(case, labels[case.case_id], row["execution"])
        print(
            f"{case.case_id}: "
            + (", ".join(f["tag"] for f in row["failures"]) or "auto_pass / review_pending"),
            flush=True,
        )
    run["summary"] = aggregate(run["cases"])
    save_run(output, run)
    write_json(output / "reviews.json", review_template(run))
    if baseline:
        comparison = compare_runs(baseline, run)
        write_json(output / "comparison.json", comparison)
        print(f"回归 {len(comparison['regressions'])}，改善 {len(comparison['improvements'])}")
    print(f"报告：{output.resolve() / 'report.md'}")
    print(
        f"自动通过 {run['summary']['auto_passed']}/{len(cases)}；"
        f"语义待人工复核 {run['summary']['review_pending']}"
    )
    return quality_exit(run)


def review_command(args):
    run = read_json(result_file(args.run))
    output = new_directory(args.output)
    apply_reviews(run, read_json(args.reviews))
    save_run(output, run)
    print(f"已应用人工复核：{output.resolve() / 'report.md'}")
    return quality_exit(run)


def compare_command(args):
    comparison = compare_runs(
        read_json(result_file(args.baseline)), read_json(result_file(args.current))
    )
    if args.output:
        path = Path(args.output)
        if path.exists():
            raise ValueError("比较文件已存在，请使用新路径")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, comparison)
    print(
        f"回归 {len(comparison['regressions'])}，改善 {len(comparison['improvements'])}，"
        f"仍失败 {len(comparison['unresolved'])}，待人工复核 {comparison['review_pending']}"
    )
    for row in comparison["regressions"]:
        print(f"REGRESSION {row['case_id']}: {', '.join(row['added'])}")
    return 1 if comparison["regressions"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="DevFlow 评测 → 定位失败 → 改进 → 回归")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="执行固定案例并保存报告/失败列表/人工复核模板")
    run.add_argument("--dataset", default=str(PROJECT_ROOT / "evals/devflow-v1"))
    run.add_argument("--split", choices=["dev", "holdout", "all"], default="dev")
    run.add_argument("--case", action="append", help="指定案例，可重复")
    run.add_argument("--cases-from", help="从 failures.json 重跑失败案例")
    run.add_argument("--provider", choices=["fake", "configured"], default="fake")
    run.add_argument("--baseline", help="同一组题的历史 results.json 或目录")
    run.add_argument("--output", help="新建的结果目录；默认 data/evals/随机运行 ID")
    run.set_defaults(handler=run_command)
    review = commands.add_parser("review", help="绑定人工语义复核，保存为新的结果目录")
    review.add_argument("--run", required=True)
    review.add_argument("--reviews", required=True)
    review.add_argument("--output", required=True)
    review.set_defaults(handler=review_command)
    compare = commands.add_parser("compare", help="逐题检测退步；退出 0 仅表示无新增退步")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--current", required=True)
    compare.add_argument("--output")
    compare.set_defaults(handler=compare_command)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
