# 文件用途：定义可核验的 PR/CI 报告，拒绝未读证据与越界行号，并生成 Markdown 草稿。
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devflow.errors import DomainError


class ReportContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(ReportContract):
    evidence_id: UUID
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_line < self.start_line:
            raise ValueError("引用结束行不能小于起始行")
        return self


class Finding(ReportContract):
    title: str = Field(min_length=1, max_length=200)
    severity: Literal["critical", "high", "medium", "low", "info"]
    explanation: str = Field(min_length=1, max_length=4000)
    evidence: list[Citation] = Field(min_length=1, max_length=10)
    suggestion: str = Field(min_length=1, max_length=2000)


class AnalysisReport(ReportContract):
    task_type: Literal["pr_review", "ci_debug", "knowledge_qa"]
    summary: str = Field(min_length=1, max_length=4000)
    findings: list[Finding] = Field(max_length=20)
    answer: str | None = Field(default=None, max_length=6000)
    answer_evidence: list[Citation] = Field(default_factory=list, max_length=12)
    failure_stage: str | None = Field(default=None, max_length=300)
    verification_steps: list[str] = Field(min_length=1, max_length=12)
    suggestions: list[str] = Field(max_length=12)
    unconfirmed: list[str] = Field(max_length=20)
    scope: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def ci_stage(self):
        if self.task_type == "ci_debug" and not self.failure_stage:
            raise ValueError("CI 报告需要失败阶段，无法判断时填写未知")
        if self.task_type == "knowledge_qa" and not self.answer:
            raise ValueError("知识问答需要 answer；没有依据时说明证据不足")
        if (
            self.task_type == "knowledge_qa"
            and not self.answer_evidence
            and "证据不足" not in self.answer
        ):
            raise ValueError("没有文档引用时必须明确说明证据不足")
        return self


def validate_citations(report, gateway, task_type):
    if report.task_type != task_type:
        raise ValueError("报告任务类型不匹配")
    for citations in [report.answer_evidence, *[finding.evidence for finding in report.findings]]:
        for citation in citations:
            key = str(citation.evidence_id)
            item = gateway.evidence.get(key)
            if item is None or not (
                item["start_line"] <= citation.start_line <= citation.end_line <= item["end_line"]
            ):
                raise ValueError("引用不属于当前任务证据或行号越界")
            if not any(
                start <= citation.start_line <= citation.end_line <= end
                for start, end in gateway.observed.get(key, [])
            ):
                raise ValueError("引用片段未被工具实际读取")


def markdown_text(value):
    # 导出内容作为 Markdown 文本，不允许模型插入 HTML、链接或改变草稿结构。
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", str(value)).replace("\n", " ")


def report_markdown(report: AnalysisReport, result: dict, run_id: str) -> str:
    lines = [
        {"pr_review": "# PR 风险审查", "ci_debug": "# CI 排障", "knowledge_qa": "# 项目知识问答"}[
            report.task_type
        ],
        "",
        "> 分析建议 · 评论草稿；请人工核验后采用。",
        "",
        f"任务：{run_id}",
        f"模型：{markdown_text(result.get('model', 'unknown'))} / "
        f"{markdown_text(result.get('provider', 'unknown'))}",
        f"固定输入：{markdown_text(result.get('input_version', {}))}",
        "",
        "## 摘要",
        markdown_text(report.summary),
    ]
    if report.failure_stage:
        lines += ["", "失败阶段：" + markdown_text(report.failure_stage)]
    if report.answer:
        lines += ["", "## 回答", markdown_text(report.answer)]
        for citation in report.answer_evidence:
            lines += [f"- 证据 {citation.evidence_id} · L{citation.start_line}–{citation.end_line}"]
    lines += ["", "## 补充发现" if report.task_type == "knowledge_qa" else "## 风险与根因假设"]
    if not report.findings:
        lines += [
            "无补充发现，请核查回答引用与未确认事项。"
            if report.task_type == "knowledge_qa"
            else "当前检查范围内未确认风险；这不代表没有缺陷。"
        ]
    for item in report.findings:
        lines += [
            "",
            f"### [{item.severity}] {markdown_text(item.title)}",
            markdown_text(item.explanation),
            "建议：" + markdown_text(item.suggestion),
        ]
        for citation in item.evidence:
            lines += [f"- 证据 {citation.evidence_id} · L{citation.start_line}–{citation.end_line}"]
    for title, items in (
        ("验证步骤", report.verification_steps),
        ("修复建议", report.suggestions),
        ("未确认事项", report.unconfirmed),
        ("检查范围", report.scope),
    ):
        lines += ["", "## " + title, *["- " + markdown_text(item) for item in items]]
    return "\r\n".join(lines) + "\r\n"


def require_report(run):
    if run.status != "succeeded" or not run.result or run.result.get("kind") != "analysis_report":
        raise DomainError(409, "report_unavailable", "任务尚无可导出的分析报告")
    return AnalysisReport.model_validate(run.result["report"])
