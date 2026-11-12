# 文件用途：区分事实、推测和建议；只按工具记录确认读取范围，不把引用有效当成结论正确。
from copy import deepcopy
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from devflow.reports import AnalysisReport, Citation, Finding, ReportContract, validate_citations
from devflow.security import redact
from devflow.tool_gateway import original_lines


class DirectEvidence(ReportContract):
    citation: Citation
    quote: str = Field(min_length=1, max_length=2000)
    observation: str = Field(min_length=1, max_length=2000)


class FindingV2(Finding):
    nature: Literal["fact", "hypothesis", "suggestion"]
    basis: Literal["current", "reference"]
    claim_type: Literal["code_behavior", "run_result", "document_statement", "follow_up"]
    root_cause: str = Field(min_length=1, max_length=300)
    direct_evidence: list[DirectEvidence] = Field(min_length=1, max_length=200)
    prerequisites: list[str] = Field(max_length=30)
    unconfirmed_conditions: list[str] = Field(max_length=30)
    severity_reason: str = Field(min_length=1, max_length=2000)
    consequences: list[str] = Field(min_length=1, max_length=100)
    reachability: Literal["local", "system", "unknown"]
    call_chain: list[Citation] = Field(max_length=100)
    evidence: list[Citation] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def boundaries(self):
        if self.nature == "hypothesis" and not self.unconfirmed_conditions:
            raise ValueError("推测必须说明还没有确认的条件")
        if self.nature == "fact" and self.basis == "reference":
            raise ValueError("历史线索不能写成本次已确认的问题")
        if self.nature == "fact" and self.claim_type == "follow_up":
            raise ValueError("待查线索不能列为事实")
        if self.nature == "suggestion" and self.severity != "info":
            raise ValueError("建议使用 info，不计为新增缺陷")
        if self.reachability == "system" and not self.call_chain:
            raise ValueError("断言系统层面可触发，必须提供当前代码调用链")
        return self


class BoundaryClaim(ReportContract):
    kind: Literal["source_truncated", "reading_incomplete"]
    evidence_id: UUID


class ReportDraftV2(AnalysisReport):
    report_version: Literal["2"]
    findings: list[FindingV2] = Field(max_length=20)
    boundary_claims: list[BoundaryClaim] = Field(max_length=40)


class ReadState(ReportContract):
    evidence_id: UUID
    path: str
    stored_start: int
    stored_end: int
    read_ranges: list[tuple[int, int]]
    reading_complete: bool
    source_truncated: bool | None


class EvidenceFacts(ReportContract):
    collection_complete: bool | None
    knowledge_enabled: bool | None
    current_versions: list[dict]
    reads: list[ReadState]


class SemanticReview(ReportContract):
    status: Literal["not_reviewed", "supported", "partial", "unsupported"] = "not_reviewed"
    reviewer: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def signed(self):
        if self.status != "not_reviewed" and (not self.reviewer or not self.notes):
            raise ValueError("结论复核必须记录复核者和依据")
        return self


class FindingResultV2(FindingV2):
    citation_check: Literal["passed"]
    semantic_support: SemanticReview


class ReportV2(ReportDraftV2):
    findings: list[FindingResultV2] = Field(max_length=20)
    evidence_facts: EvidenceFacts
    citation_check: Literal["passed"]
    semantic_support: SemanticReview


PublicReport = AnalysisReport | ReportV2


def parse_report(value):
    if value.get("report_version") == "2":
        schema = ReportV2 if "evidence_facts" in value else ReportDraftV2
        return schema.model_validate(value)
    return AnalysisReport.model_validate(value)


def evidence_facts(gateway):
    version = gateway.metadata.get("input_version", {})
    resources = version.get("resources", [])
    coverage = [r.get("coverage_complete") for r in resources]
    complete = (
        False
        if False in coverage
        else True
        if coverage and all(v is True for v in coverage)
        else None
    )
    versions = []
    for resource in resources:
        if resource.get("head_sha"):
            versions.append(
                {
                    "kind": resource.get("kind"),
                    "head": resource["head_sha"],
                    "base": resource.get("base_sha"),
                    "version_kind": gateway.metadata.get("version_kind", "fixed_input"),
                }
            )
    reads = []
    for key, item in gateway.evidence.items():
        start, end = item["start_line"], min(item["end_line"], len(original_lines(item["content"])))
        ranges = sorted({tuple(pair) for pair in gateway.observed.get(key, [])})
        cursor = start
        for left, right in ranges:
            if left > cursor:
                break
            cursor = max(cursor, right + 1)
        # 只有采集适配器明确记录才知道源材料是否截断。next_line 和正文长短都不能证明。
        truncated = item.get("capture_truncated")
        reads.append(
            ReadState(
                evidence_id=key,
                path=item["path"],
                stored_start=start,
                stored_end=end,
                read_ranges=ranges,
                reading_complete=cursor > end,
                source_truncated=truncated if isinstance(truncated, bool) else None,
            )
        )
    enabled = version.get("use_knowledge")
    return EvidenceFacts(
        collection_complete=complete,
        knowledge_enabled=enabled if isinstance(enabled, bool) else None,
        current_versions=versions,
        reads=reads,
    )


def current_evidence(item, gateway, task_type):
    # 文档和历史记忆可说明约束，不能单独证明当前 PR/CI 已经出现缺陷。
    if task_type == "knowledge_qa":
        return item["source_type"] == "document"
    resources = gateway.metadata.get("input_version", {}).get("resources", [])
    for resource in resources:
        head = resource.get("head_sha")
        if not head:
            continue
        if item["source_type"] == "file" and item["version"] == head:
            return True
        if item["source_type"] == "diff" and item["version"] in {
            head,
            f"{resource.get('base_sha')}..{head}",
        }:
            return True
        if item["source_type"] == "log" and (
            item["version"] == head
            or item["version"].startswith(
                head + ":attempt-" + str(resource.get("run_attempt")) + ":job-"
            )
        ):
            return True
    return False


def validate_report_v2(report, gateway, task_type):
    validate_citations(report, gateway, task_type)
    facts = evidence_facts(gateway)
    reads = {str(r.evidence_id): r for r in facts.reads}
    for finding in report.findings:
        all_citations = [d.citation for d in finding.direct_evidence] + finding.call_chain
        # 引用检查覆盖新字段，不能通过把未读行移到“直接证据”或“调用链”绕过。
        validate_citations(
            report.model_copy(update={"answer_evidence": all_citations}), gateway, task_type
        )
        for direct in finding.direct_evidence:
            if not any(
                c.evidence_id == direct.citation.evidence_id
                and c.start_line
                <= direct.citation.start_line
                <= direct.citation.end_line
                <= c.end_line
                for c in finding.evidence
            ):
                raise ValueError("直接证据必须同时出现在该项引用列表中")
            item = gateway.evidence[str(direct.citation.evidence_id)]
            text = "\n".join(
                original_lines(item["content"])[
                    direct.citation.start_line - 1 : direct.citation.end_line
                ]
            )
            if direct.quote.replace("\r\n", "\n") not in redact(text):
                raise ValueError("直接证据中的原文必须确实出现在所引行中")
        if finding.basis == "current":
            allowed_sources = {
                "code_behavior": {"file", "diff"},
                "run_result": {"log"},
                "document_statement": {"document"} if task_type == "knowledge_qa" else set(),
                "follow_up": {"file", "diff", "log", "document"},
            }[finding.claim_type]
            if not any(
                (item := gateway.evidence[str(d.citation.evidence_id)])["source_type"]
                in allowed_sources
                and current_evidence(item, gateway, task_type)
                for d in finding.direct_evidence
            ):
                raise ValueError(
                    "没有当前版本的对应直接证据，历史资料只能作为待查线索；代码判断需要当前代码"
                )
        if finding.reachability == "system" and not all(
            gateway.evidence[str(c.evidence_id)]["source_type"] == "file"
            and current_evidence(gateway.evidence[str(c.evidence_id)], gateway, task_type)
            for c in finding.call_chain
        ):
            raise ValueError("调用链必须引用本次提交中已读的代码")
    for claim in report.boundary_claims:
        state = reads.get(str(claim.evidence_id))
        if state is None:
            raise ValueError("范围说明引用了任务之外的材料")
        if claim.kind == "source_truncated" and state.source_truncated is not True:
            raise ValueError("没有明确采集标记，不能断言原始材料被截断")
        if claim.kind == "reading_incomplete" and state.reading_complete:
            raise ValueError("已读完所保存材料，不能声称工具未读完")


def _unique(items):
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def finalize_report(report, gateway, task_type):
    validate_report_v2(report, gateway, task_type)
    # 依据模型声明的共同根因合并；不凭关键词猜测两个问题是否相同。
    groups = {}
    for finding in report.findings:
        groups.setdefault((finding.root_cause.strip().casefold(), finding.basis), []).append(
            finding
        )
    merged = []
    rank = ["info", "low", "medium", "high", "critical"]
    for items in groups.values():
        risks = [v for v in items if v.nature != "suggestion"]
        primary = deepcopy((risks or items)[0])
        selected = risks or items
        primary.nature = (
            "hypothesis" if any(v.nature == "hypothesis" for v in selected) else primary.nature
        )
        primary.severity = max((v.severity for v in selected), key=rank.index)
        for key in (
            "evidence",
            "direct_evidence",
            "prerequisites",
            "unconfirmed_conditions",
            "consequences",
            "call_chain",
        ):
            setattr(primary, key, _unique([v for item in items for v in getattr(item, key)]))
        primary.explanation = "\n".join(_unique([v.explanation for v in selected]))
        primary.suggestion = "\n".join(_unique([v.suggestion for v in items]))
        primary.severity_reason = "\n".join(_unique([v.severity_reason for v in selected]))
        merged.append(
            FindingResultV2(
                **primary.model_dump(), citation_check="passed", semantic_support=SemanticReview()
            )
        )
    return ReportV2(
        **{**report.model_dump(), "findings": merged},
        evidence_facts=evidence_facts(gateway),
        citation_check="passed",
        semantic_support=SemanticReview(),
    )
