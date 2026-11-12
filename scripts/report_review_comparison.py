# 文件用途：汇总同一初稿复核前后的GPT判断，拒绝复用其他输出的复核记录。
import argparse
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median

from devflow.evaluation import digest, read_json, write_json

CATEGORIES = {
    "metadata_conflict",
    "truncation",
    "unsupported_cause",
    "historical_only",
    "duplicate",
    "overstated_impact",
    "unsupported_advice",
    "calculation",
}


def summarize(directory, reviews):
    directory = Path(directory)
    state = read_json(directory / "state.json")
    if state["completed"] != state["cases"]:
        raise ValueError("计划题目未全部完成，不能作为完整对比")
    if reviews["fingerprint"] != state["fingerprint"] or reviews["reviewer"] != "GPT":
        raise ValueError("复核不属于该次固定对比")
    entries = {r["case_id"]: r for r in reviews["cases"]}
    if len(entries) != len(reviews["cases"]) or set(entries) != set(state["cases"]):
        raise ValueError("GPT复核必须与全部题目一一对应")
    rows = []
    regressions = []
    for name in state["cases"]:
        job = read_json(directory / "jobs" / (name + ".json"))
        review = entries[name]
        for phase in ["before", "after"]:
            if (
                digest(job[phase]) != job[phase + "_sha256"]
                or review[phase + "_sha256"] != job[phase + "_sha256"]
            ):
                raise ValueError("输入输出已改变，不能沿用旧复核")
            score = review[phase]
            if (
                score["verdict"] not in {"pass", "pass_with_notes", "fail", "no_report"}
                or not score["notes"].strip()
            ):
                raise ValueError("必须逐题说明结论与依据")
            if not isinstance(score["abstained"], bool):
                raise ValueError("拒答必须逐题判断，不能按关键词猜测")
            for issue in score["target_errors"]:
                if (
                    issue["category"] not in CATEGORIES
                    or not issue["reason"].strip()
                    or not issue["evidence_refs"]
                ):
                    raise ValueError("目标错误需要分类、原因和原文位置")
            if score["target_errors"] and score["verdict"] in {"pass", "pass_with_notes"}:
                raise ValueError("实质目标错误不能同时标成通过")
        previous, current = review["before"], review["after"]
        if previous["verdict"] in {"pass", "pass_with_notes"} and current["verdict"] in {
            "fail",
            "no_report",
        }:
            if not review.get("regression_reason", "").strip():
                raise ValueError("已通过题目退步必须解释具体原因")
            regressions.append({"case_id": name, "reason": review["regression_reason"]})
        record = job["after"].get("result", {}).get("report_review")
        if record:
            if record["output_report_sha256"] != digest(job["after"]["result"]["report"]):
                raise ValueError("复核后报告编号不一致")
            if record["input_report_sha256"] != digest(record["initial_report"]):
                raise ValueError("复核前报告编号不一致")
            if (
                record["review_calls"] > 1
                or record["revision_calls"] > 1
                or record["supplement_rounds"] > 1
            ):
                raise ValueError("复核或补查次数超限")
        rows.append((job, review))
    result = {
        "cases": len(rows),
        "fingerprint": state["fingerprint"],
        "reviewer": "GPT",
        "regressions": regressions,
        "blind": False,
        "comparison": state["comparison"],
    }
    for phase in ["before", "after"]:
        scores = [r[phase] for _, r in rows]
        executions = [j[phase] for j, _ in rows]
        categories = Counter(c for s in scores for c in {e["category"] for e in s["target_errors"]})
        result[phase] = {
            "verdicts": dict(Counter(s["verdict"] for s in scores)),
            "target_error_cases": sum(bool(s["target_errors"]) for s in scores),
            "target_category_occurrences": sum(categories.values()),
            "target_categories": dict(categories),
            "abstentions": sum(s["abstained"] for s in scores),
            "false_positive_cases": sum(s["false_positive"] is True for s in scores),
            "missed_issue_cases": sum(s["missed_issue"] is True for s in scores),
            "duration_ms_median": median(e["duration_ms"] for e in executions),
            "duration_ms_total": sum(e["duration_ms"] for e in executions),
            "input_tokens": sum(e["usage"]["prompt_tokens"] for e in executions),
            "output_tokens": sum(e["usage"]["completion_tokens"] for e in executions),
            "known_cost_cny": str(
                sum(
                    (
                        Decimal(e["known_usage_cost_cny"])
                        for e in executions
                        if e["known_usage_cost_cny"] is not None
                    ),
                    Decimal(0),
                )
            ),
            "unknown_usage_cases": sum(e["usage_unknown"] for e in executions),
        }
    result["review_statuses"] = dict(
        Counter(
            j["after"].get("result", {}).get("report_review", {}).get("status", "no_report")
            for j, _ in rows
        )
    )
    result["supplement_rounds"] = sum(
        j["after"].get("result", {}).get("report_review", {}).get("supplement_rounds", 0)
        for j, _ in rows
    )
    result["billing"] = {
        "settled_cny": str(
            sum(
                (
                    Decimal(c["settled_cny"])
                    for j, _ in rows
                    for c in j["billing"]
                    if c["settled_cny"] is not None
                ),
                Decimal(0),
            )
        ),
        "unsettled_requests": sum(c["settled_cny"] is None for j, _ in rows for c in j["billing"]),
    }
    result["acceptance"] = {
        "target_errors_reduced": result["after"]["target_category_occurrences"]
        < result["before"]["target_category_occurrences"]
        and result["after"]["target_error_cases"] <= result["before"]["target_error_cases"],
        "no_unexplained_regressions": True,
        "no_extra_missing_reports": result["after"]["verdicts"].get("no_report", 0)
        <= result["before"]["verdicts"].get("no_report", 0),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="汇总已绑定原文的GPT逐题复核，不调用模型")
    parser.add_argument("--directory", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = summarize(args.directory, read_json(args.reviews))
    write_json(args.output, result)
    print(result)
    return 0 if all(result["acceptance"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
