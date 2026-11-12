# 文件用途：汇总真实基线的工程指标与已绑定哈希的GPT复核，不用自动规则代替语义判断。
import argparse
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import mean, median

from devflow.evaluation import digest, read_json, write_json


def summarize(directory, review_file=None):
    directory = Path(directory)
    state = read_json(directory / "state.json")
    if state["configuration"]["provider"] == "fake":
        raise ValueError("本工具只汇总真实基线，不将fake的零token写为真实成本")
    rows = [read_json(directory / "jobs" / f"{job}.json") for job in state["completed"]]
    if len({r["job_id"] for r in rows}) != len(rows):
        raise ValueError("重复job")
    review = read_json(review_file) if review_file else None
    reviews = {r["job_id"]: r for r in review["cases"]} if review else {}
    if review and len(reviews) != len(review["cases"]):
        raise ValueError("复核job重复")
    known = {r["job_id"]: r for r in rows}
    for key, value in reviews.items():
        if key not in known or value["execution_sha256"] != digest(known[key]["execution"]):
            raise ValueError(f"复核输出哈希不匹配: {key}")
        if value["case_sha256"] != known[key]["case_sha256"]:
            raise ValueError(f"复核输入哈希不匹配: {key}")
    groups = {}
    for arm in sorted({j["arm"] for j in state["jobs"]}):
        selected = [r for r in rows if r["arm"] == arm]
        engineering = {
            "planned": sum(j["arm"] == arm for j in state["jobs"]),
            "executed": len(selected),
            "valid_reports": 0,
            "errors": Counter(),
            "automatic_failure_tags": Counter(),
            "citations": 0,
            "valid_citations": 0,
            "reports_with_citations": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "usage_unknown_jobs": 0,
            "settled_cost_cny": Decimal(0),
            "unresolved_reservation_cny": Decimal(0),
            "model_requests": 0,
            "estimated_tokens_saved_across_requests": 0,
        }
        semantics = {
            "reviewed": 0,
            "pending": 0,
            "verdicts": Counter(),
            "core_correct": 0,
            "core_incorrect": 0,
            "core_not_assessable": 0,
            "pr_positive_cases": 0,
            "pr_primary_detected": 0,
            "pr_primary_not_assessable": 0,
            "pr_primary_false_negatives": 0,
            "pr_clean_cases": 0,
            "pr_clean_false_positive_reports": 0,
            "pr_unsupported_findings": 0,
            "ci_cases": 0,
            "ci_stage_correct": 0,
            "ci_root_or_uncertainty_appropriate": 0,
            "ci_stage_proxy_false_failures": 0,
        }
        for row in selected:
            execution = row["execution"]
            report = execution["result"].get("report")
            if execution["error"]:
                engineering["errors"][execution["error"]["code"]] += 1
            else:
                engineering["valid_reports"] += 1
            engineering["automatic_failure_tags"].update(f["tag"] for f in row["automatic_checks"])
            for key in ["prompt_tokens", "completion_tokens"]:
                engineering[key] += execution["usage"][key]
            engineering["usage_unknown_jobs"] += bool(execution["usage_unknown"])
            engineering["model_requests"] += len(row["billing"])
            for charge in row["billing"]:
                if charge["settled_cny"] is not None:
                    engineering["settled_cost_cny"] += Decimal(charge["settled_cny"])
                elif charge["status"] in {"reserved", "inflight", "uncertain"}:
                    engineering["unresolved_reservation_cny"] += Decimal(charge["reserved_cny"])
            engineering["estimated_tokens_saved_across_requests"] += sum(
                c.get("context", {}).get("saved_tokens", 0) for c in execution["trace"]["calls"]
            )
            if report:
                citations = [
                    *report["answer_evidence"],
                    *[c for f in report["findings"] for c in f["evidence"]],
                ]
                engineering["reports_with_citations"] += bool(citations)
                evidence = {e["id"]: e for e in execution["evidence"]}
                for citation in citations:
                    engineering["citations"] += 1
                    item = evidence.get(citation["evidence_id"])
                    engineering["valid_citations"] += bool(
                        item
                        and item["start_line"]
                        <= citation["start_line"]
                        <= citation["end_line"]
                        <= item["end_line"]
                        and any(
                            a <= citation["start_line"] <= citation["end_line"] <= b
                            for a, b in execution["observed"].get(item["id"], [])
                        )
                    )
            value = reviews.get(row["job_id"])
            if not value:
                semantics["pending"] += 1
                continue
            semantics["reviewed"] += 1
            semantics["verdicts"][value["verdict"]] += 1
            correct = value["core_correct"]
            semantics[
                "core_correct"
                if correct is True
                else "core_incorrect"
                if correct is False
                else "core_not_assessable"
            ] += 1
            if "primary_issue_detected" in value:
                positive = bool(row["expectation"]["expected_findings"])
                semantics["pr_positive_cases"] += positive
                semantics["pr_primary_detected"] += (
                    positive and value["primary_issue_detected"] is True
                )
                semantics["pr_primary_not_assessable"] += (
                    positive and value["primary_issue_detected"] is None
                )
                semantics["pr_clean_cases"] += not positive
                semantics["pr_primary_false_negatives"] += value["false_negative_primary"]
                semantics["pr_unsupported_findings"] += value["unsupported_finding_count"]
                semantics["pr_clean_false_positive_reports"] += bool(
                    not positive and value["unsupported_finding_count"]
                )
            if "stage_correct" in value:
                semantics["ci_cases"] += 1
                semantics["ci_stage_correct"] += value["stage_correct"] is True
                semantics["ci_root_or_uncertainty_appropriate"] += (
                    value["root_or_uncertainty_appropriate"] is True
                )
                semantics["ci_stage_proxy_false_failures"] += value["stage_proxy_false_failure"]
        times = [r["execution"]["duration_ms"] for r in selected]
        engineering["duration_ms"] = (
            {"mean": mean(times), "median": median(times), "min": min(times), "max": max(times)}
            if times
            else None
        )
        for key in ["settled_cost_cny", "unresolved_reservation_cny"]:
            engineering[key] = str(engineering[key])
        groups[arm] = {"engineering": engineering, "semantic": semantics}
    retrieval_path = directory / "retrieval.json"
    retrieval = read_json(retrieval_path) if retrieval_path.exists() else None
    retrieval_summary = {}
    if retrieval:
        for mode in ["keyword", "hybrid"]:
            items = [r for r in retrieval["rows"] if r["mode"] == mode]
            scores = [r["recall_at_6"] for r in items if r["recall_at_6"] is not None]
            retrieval_summary[mode] = {
                "relevant_queries": len(scores),
                "no_relevant_document_queries": sum(r["no_relevant_documents"] for r in items),
                "mean_recall_at_6": mean(scores) if scores else None,
            }
    return {
        "cohort": str(directory),
        "suite": state["suite"],
        "dataset": state["dataset"],
        "provenance": state["provenance"],
        "configuration": state["configuration"],
        "groups": groups,
        "fixed_question_retrieval": retrieval_summary,
        "reviewer": review["reviewer"] if review else None,
        "review_file": str(review_file) if review_file else None,
        "stop_history": state.get("stop_history", []),
        "limitations": [
            "目录价usage估算，不代表供应商最终账单；未知费用保留预留，不计为零。",
            "引用身份/范围有效不等于语义支持；空引用不计入引用有效率分母。",
            "GPT为用户授权复核者，并非独立实体人类盲审。",
            "耗时包含工具与网络；并发工程任务和批次时段不同，不作严格性能基准。",
            "小型固定语料Recall饱和不证明混合检索具有一般优势。",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--review")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, summarize(args.directory, args.review))
    print(output)


if __name__ == "__main__":
    main()
