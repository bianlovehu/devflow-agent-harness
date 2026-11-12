# 文件用途：校验固定评测集、独立检查证据、绑定人工复核并按逐题结果检测回归。
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.report_v2 import parse_report

EVALUATOR_VERSION = "devflow-evaluator-v2"

FAILURE_HINTS = {
    "execution": "先查 trace 的错误码和最后一次模型/工具调用。",
    "schema": "检查报告 schema、任务类型和一次格式修正记录。",
    "citation": "检查证据 ID、实际读取区间和引用行号；不要引用目录或其他版本。",
    "evidence_miss": "查看 required_evidence 与工具读取记录，区分没读到和读到后没引用。",
    "false_positive": "对比 base/head，只报告本次新增且有证据支持的问题。",
    "missed_issue": "核查变更行和契约；需要语义复核确认是否漏报。",
    "wrong_stage": "对照原始日志，区分失败步骤与后续退出摘要。",
    "abstention": "材料不足时明确给出未知/证据不足和需要补充的材料。",
    "semantic": "对照预期结论和禁止结论，由人工定位语义错误。",
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    key: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    source_type: Literal["file", "diff", "log", "document"]
    path: str
    revision: Literal["base", "head"]
    content: str = Field(min_length=1)


class Case(Strict):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    source_group: str
    split: Literal["dev", "holdout"]
    task_type: Literal["pr_review", "ci_debug", "knowledge_qa"]
    question: str = Field(min_length=1)
    sources: list[Source]

    @model_validator(mode="after")
    def unique_sources(self):
        if len({s.key for s in self.sources}) != len(self.sources):
            raise ValueError("重复 source key")
        return self


class Anchor(Strict):
    source_key: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class Expectation(Strict):
    case_id: str
    expected_findings: list[str]
    required_evidence: list[Anchor]
    must_not_conclude: list[str]
    allow_uncertain: str
    requires_abstention: bool = False
    allowed_stages: list[str] = Field(default_factory=list)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\r\n",
    )


def load_dataset(directory):
    raw_inputs = read_json(Path(directory) / "inputs.json")
    raw_labels = read_json(Path(directory) / "expectations.json")
    if raw_inputs["schema_version"] != 1 or raw_labels["schema_version"] != 1:
        raise ValueError("不支持的数据集 schema")
    if raw_inputs["dataset_version"] != raw_labels["dataset_version"]:
        raise ValueError("输入与标注版本不一致")
    cases = [Case.model_validate(c) for c in raw_inputs["cases"]]
    expectations = [Expectation.model_validate(c) for c in raw_labels["cases"]]
    keys = {c.case_id for c in cases}
    if (
        not cases
        or len(keys) != len(cases)
        or len(expectations) != len(keys)
        or {e.case_id for e in expectations} != keys
    ):
        raise ValueError("案例 ID 重复或输入/标注不一一对应")
    groups = {}
    labels = {e.case_id: e for e in expectations}
    for case in cases:
        if groups.setdefault(case.source_group, case.split) != case.split:
            raise ValueError("同一来源不能跨开发集和留出集")
        sources = {s.key: s for s in case.sources}
        for anchor in labels[case.case_id].required_evidence:
            source = sources.get(anchor.source_key)
            if source is None or not 1 <= anchor.start_line <= anchor.end_line <= len(
                source.content.splitlines()
            ):
                raise ValueError(f"无效参考证据：{case.case_id}")
    return (
        cases,
        labels,
        {
            "version": raw_inputs["dataset_version"],
            "sha256": digest({"inputs": raw_inputs, "labels": raw_labels}),
        },
    )


def grade(case, expected, execution):
    """自动检查只衡量结构和证据覆盖；不能证明引用支持语义结论。"""
    failures = []

    def fail(tag, detail, check_id=None):
        failures.append(
            {
                "tag": tag,
                "check_id": check_id or tag,
                "detail": detail,
                "next_step": FAILURE_HINTS[tag],
            }
        )

    if execution.get("error"):
        fail("execution", execution["error"])
        return failures
    try:
        report = parse_report(execution["result"]["report"])
        if report.task_type != case.task_type:
            raise ValueError("报告任务类型与案例不同")
    except (ValueError, KeyError, TypeError) as error:
        fail("schema", str(error))
        return failures
    evidence = {e["id"]: e for e in execution["evidence"]}
    findings = [
        f
        for f in report.findings
        if getattr(f, "nature", None) != "suggestion"
        and getattr(f, "basis", "current") == "current"
    ]
    relevant = {c.model_dump_json() for f in findings for c in f.evidence} | {
        c.model_dump_json() for c in report.answer_evidence
    }
    citations = [c for f in report.findings for c in f.evidence] + report.answer_evidence
    for finding in report.findings:
        citations += [d.citation for d in getattr(finding, "direct_evidence", [])]
        citations += getattr(finding, "call_chain", [])
    citations = list({c.model_dump_json(): c for c in citations}.values())
    valid = []
    for citation in citations:
        key = str(citation.evidence_id)
        item = evidence.get(key)
        if (
            item is None
            or not item["start_line"]
            <= citation.start_line
            <= citation.end_line
            <= item["end_line"]
            or not any(
                start <= citation.start_line <= citation.end_line <= end
                for start, end in execution["observed"].get(key, [])
            )
        ):
            fail(
                "citation",
                citation.model_dump(mode="json"),
                "citation:" + digest(citation.model_dump(mode="json")),
            )
        elif citation.model_dump_json() in relevant:
            valid.append((item, citation))
    for anchor in expected.required_evidence:
        if not any(
            item["source_key"] == anchor.source_key
            and citation.start_line <= anchor.start_line
            and citation.end_line >= anchor.end_line
            for item, citation in valid
        ):
            read = any(
                item["source_key"] == anchor.source_key
                and any(
                    start <= anchor.start_line <= anchor.end_line <= end
                    for start, end in execution["observed"].get(item["id"], [])
                )
                for item in evidence.values()
            )
            fail(
                "evidence_miss",
                {**anchor.model_dump(), "read_by_tool": read},
                f"evidence_miss:{anchor.source_key}:{anchor.start_line}:{anchor.end_line}",
            )
    if case.task_type == "pr_review" and not expected.expected_findings and findings:
        fail("false_positive", f"正常/修复 PR 产生 {len(findings)} 项发现")
    if case.task_type != "knowledge_qa" and expected.expected_findings and not findings:
        fail("missed_issue", "预期有问题，但 findings 为空；需人工核查")
    if expected.allowed_stages and report.failure_stage not in expected.allowed_stages:
        fail("wrong_stage", {"actual": report.failure_stage, "allowed": expected.allowed_stages})
    text = " ".join([report.answer or "", report.failure_stage or "", *report.unconfirmed])
    if expected.requires_abstention and not any(
        word in text for word in ["证据不足", "无法确定", "未知", "不能确认"]
    ):
        fail("abstention", "材料不足题未明确表达无法确认")
    return failures


def aggregate(rows):
    return {
        "cases": len(rows),
        "auto_passed": sum(not r["failures"] for r in rows),
        "auto_failed": sum(bool(r["failures"]) for r in rows),
        "review_pending": sum(r["review"]["verdict"] == "pending" for r in rows),
        "human_passed": sum(r["review"]["verdict"] == "pass" for r in rows),
        "human_failed": sum(r["review"]["verdict"] == "fail" for r in rows),
        "failure_tags": dict(Counter(f["tag"] for r in rows for f in r["failures"])),
        "duration_ms": round(sum(r["execution"]["duration_ms"] for r in rows)),
        "tokens": sum(
            r["execution"]
            .get("usage", r["execution"].get("result", {}).get("usage", {}))
            .get("total_tokens", 0)
            for r in rows
        ),
        "usage_unknown_cases": sum(bool(r["execution"].get("usage_unknown")) for r in rows),
        "known_usage_cost_cny": str(
            sum(
                (
                    Decimal(r["execution"]["known_usage_cost_cny"])
                    for r in rows
                    if r["execution"].get("known_usage_cost_cny") is not None
                ),
                Decimal(0),
            )
        ),
        "cost_unavailable_cases": sum(
            r["execution"].get("known_usage_cost_cny") is None for r in rows
        ),
    }


class Review(Strict):
    case_id: str
    execution_sha256: str
    verdict: Literal["pending", "pass", "fail"]
    reviewer: str = ""
    notes: str = ""
    failure_tags: list[
        Literal[
            "missed_issue",
            "false_positive",
            "wrong_root_cause",
            "unsupported_claim",
            "bad_answer",
            "other",
        ]
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def signed(self):
        if self.verdict != "pending" and (not self.reviewer.strip() or not self.notes.strip()):
            raise ValueError("已复核结论必须填写 reviewer 和 notes")
        if self.verdict == "fail" and not self.failure_tags:
            raise ValueError("失败复核需要 failure_tags")
        if self.verdict != "fail" and self.failure_tags:
            raise ValueError("只有失败复核允许 failure_tags")
        return self


def review_template(run):
    return {
        "run_id": run["run_id"],
        "dataset_sha256": run["dataset"]["sha256"],
        "reviews": [
            {
                "case_id": r["case_id"],
                "execution_sha256": digest(r["execution"]),
                "verdict": "pending",
                "reviewer": "",
                "notes": "",
                "failure_tags": [],
            }
            for r in run["cases"]
        ],
    }


def apply_reviews(run, reviews):
    if reviews["run_id"] != run["run_id"] or reviews["dataset_sha256"] != run["dataset"]["sha256"]:
        raise ValueError("人工复核不属于此运行/数据集")
    parsed = [Review.model_validate(r) for r in reviews["reviews"]]
    mapping = {r.case_id: r for r in parsed}
    if len(mapping) != len(parsed) or set(mapping) != {r["case_id"] for r in run["cases"]}:
        raise ValueError("复核必须与运行案例一一对应")
    for row in run["cases"]:
        review = mapping[row["case_id"]]
        if review.execution_sha256 != digest(row["execution"]):
            raise ValueError("报告已变化，不能沿用旧复核")
    for row in run["cases"]:
        row["review"] = mapping[row["case_id"]].model_dump()
    run["summary"] = aggregate(run["cases"])


def compare_runs(baseline, current):
    if baseline["schema_version"] != 1 or current["schema_version"] != 1:
        raise ValueError("不支持的运行结果 schema")
    if (
        baseline.get("evaluator_version") != EVALUATOR_VERSION
        or current.get("evaluator_version") != EVALUATOR_VERSION
    ):
        raise ValueError("评分器版本不同，需使用相同评分规则重新评测")
    if baseline["dataset"] != current["dataset"]:
        raise ValueError("数据集版本或内容不同，不能比较")
    if baseline["profile"] != current["profile"]:
        raise ValueError("供应商/模型/检索适配器不同，不能作为同配置回归")
    before = {r["case_id"]: r for r in baseline["cases"]}
    after = {r["case_id"]: r for r in current["cases"]}
    if not before or before.keys() != after.keys():
        raise ValueError("回归必须包含基线中的全部同一组案例")
    changed, unresolved = [], []
    for key, old in before.items():
        new = after[key]
        if old["case_sha256"] != new["case_sha256"]:
            raise ValueError("案例输入或标注变化，不能沿用基线")
        old_tags, new_tags = (
            {f.get("check_id", f["tag"]) for f in r["failures"]} for r in [old, new]
        )
        added, removed = new_tags - old_tags, old_tags - new_tags
        # 人工判定只绑定各自输出；新输出未复核不能继续宣称语义通过。
        old_verdict, new_verdict = old["review"]["verdict"], new["review"]["verdict"]
        if old_verdict == "pass" and new_verdict != "pass":
            added.add("semantic_review_lost" if new_verdict == "pending" else "semantic")
        if old_verdict == "fail" and new_verdict == "pass":
            removed.add("semantic")
        if old_verdict != "fail" and new_verdict == "fail":
            added.add("semantic")
        if added or removed:
            changed.append({"case_id": key, "added": sorted(added), "removed": sorted(removed)})
        if new_tags or new_verdict == "fail":
            unresolved.append(key)
    return {
        "baseline_run_id": baseline["run_id"],
        "current_run_id": current["run_id"],
        "regressions": [c for c in changed if c["added"]],
        "improvements": [c for c in changed if c["removed"]],
        "unresolved": unresolved,
        "review_pending": current["summary"]["review_pending"],
    }


def render_report(run):
    summary = run["summary"]
    lines = [
        "# DevFlow 固定评测",
        "",
        f"运行：{run['run_id']}",
        f"模型：{run['profile']['provider']} / {run['profile']['model']}",
        f"数据集：{run['dataset']['version']} · {run['dataset']['sha256']}",
        f"代码：{run['provenance']['git_commit']} · dirty={run['provenance']['dirty']}",
        "",
        f"{summary['cases']} 题，自动检查通过 {summary['auto_passed']}，"
        f"失败 {summary['auto_failed']}；人工待复核 {summary['review_pending']}，"
        f"通过 {summary['human_passed']}，失败 {summary['human_failed']}。",
        "",
        "自动检查覆盖 schema、已读引用、参考证据覆盖、正常 PR 误报、"
        "CI 阶段标签和拒答措辞。证据覆盖与阶段标签是代理指标，语义结论需人工复核。",
        "假模型零 token 不代表真实模型开销；快照关键词适配器不代表生产混合检索效果。",
        "",
        f"耗时 {summary['duration_ms']} ms；已知用量 {summary['tokens']} tokens，"
        f"{summary['usage_unknown_cases']} 题存在未知 usage；"
        f"已知用量目录价估算 {summary['known_usage_cost_cny']} 元，"
        f"{summary['cost_unavailable_cases']} 题缺少报价。",
        "",
        "| 案例 | 自动检查 | 人工复核 | 失败标签 |",
        "| --- | --- | --- | --- |",
    ]
    for row in run["cases"]:
        tags = ", ".join(f["tag"] for f in row["failures"]) or "—"
        lines.append(
            f"| {row['case_id']} | {'失败' if row['failures'] else '通过'} | "
            f"{row['review']['verdict']} | {tags} |"
        )
    for row in run["cases"]:
        lines += [
            "",
            "## " + row["case_id"],
            "",
            "预期：" + ("；".join(row["expectation"]["expected_findings"]) or "无新增缺陷"),
            "允许不确定：" + row["expectation"]["allow_uncertain"],
            "禁止结论：" + "；".join(row["expectation"]["must_not_conclude"]),
            "",
            f"报告、证据、读取区间及 trace：cases/{row['case_id']}.json",
        ]
        for failure in row["failures"]:
            lines += ["", f"- {failure['tag']}：{failure['detail']}", failure["next_step"]]
    return "\n".join(lines) + "\n"


def save_run(directory, run):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cases").mkdir(exist_ok=True)
    write_json(directory / "results.json", run)
    write_json(
        directory / "failures.json",
        {
            "run_id": run["run_id"],
            "dataset": run["dataset"],
            "case_ids": [
                r["case_id"]
                for r in run["cases"]
                if r["failures"] or r["review"]["verdict"] == "fail"
            ],
            "cases": [
                {"case_id": r["case_id"], "failures": r["failures"], "review": r["review"]}
                for r in run["cases"]
                if r["failures"] or r["review"]["verdict"] == "fail"
            ],
        },
    )
    for row in run["cases"]:
        write_json(directory / "cases" / (row["case_id"] + ".json"), row)
    (directory / "report.md").write_text(render_report(run), encoding="utf-8", newline="\r\n")


def quality_exit(run):
    if run["summary"]["auto_failed"] or run["summary"]["human_failed"]:
        return 1
    return 3 if run["summary"]["review_pending"] else 0
