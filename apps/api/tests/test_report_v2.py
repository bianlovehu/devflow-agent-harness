# 文件用途：重现四类已发现的结论错误，检查新版边界、旧报告和旧任务恢复。
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from devflow.agent import AnalysisRunner, model_configuration
from devflow.config import Settings
from devflow.eval_runner import execute_case
from devflow.evaluation import grade, load_dataset
from devflow.model_gateway import ModelReply, ScriptedModel, tool_call
from devflow.report_v2 import ReportDraftV2, evidence_facts, finalize_report, parse_report
from devflow.reports import AnalysisReport, report_markdown, require_report
from devflow.tool_gateway import ToolGateway
from test_agent import answer, evidence


def setup(*, content="return list(tasks)\n", source_type="file", knowledge=False):
    item = evidence(content, source_type=source_type)
    tools = ToolGateway(
        "registered",
        [item],
        {
            "input_version": {
                "use_knowledge": knowledge,
                "resources": [
                    {
                        "kind": "pull_request",
                        "head_sha": "a" * 40,
                        "base_sha": "b" * 40,
                        "coverage_complete": True,
                    },
                ],
            }
        },
    )
    tools.execute("read_evidence", json.dumps({"repo_id": "registered", "evidence_id": item["id"]}))
    report = answer(item)
    report.update(report_version="2", boundary_claims=[])
    report["findings"][0].update(
        nature="fact",
        basis="current",
        claim_type="run_result" if source_type == "log" else "code_behavior",
        root_cause="删除所有者筛选",
        direct_evidence=[
            {
                "citation": report["findings"][0]["evidence"][0],
                "quote": content.splitlines()[0],
                "observation": "函数直接返回输入任务。",
            }
        ],
        prerequisites=["调用方传入了多个所有者的任务。"],
        unconfirmed_conditions=["尚未读取调用方，系统层面是否触发未知。"],
        severity_reason="仅确认局部筛选删除，外部访问范围尚未确认。",
        consequences=["局部函数不再按所有者筛选。"],
        reachability="local",
        call_chain=[],
    )
    return item, tools, report


def finish(value, tools):
    return finalize_report(ReportDraftV2.model_validate(value), tools, value["task_type"])


def test_common_cause_merges_consequences_but_advice_is_not_an_extra_defect():
    _, tools, value = setup()
    second = deepcopy(value["findings"][0])
    second.update(title="actor参数不再使用", consequences=["调用方参数失去筛选作用。"])
    advice = deepcopy(second)
    advice.update(
        nature="suggestion",
        severity="info",
        title="补充测试说明",
        consequences=["测试说明有助于核查隔离约束。"],
    )
    value["findings"] += [second, advice]
    result = finish(value, tools)
    assert len(result.findings) == 1 and result.findings[0].nature == "fact"
    assert len(result.findings[0].consequences) == 3
    assert len(result.findings[0].evidence) == 1
    advice["root_cause"] = "补充开发说明"
    value["findings"] = [advice]
    assert finish(value, tools).findings[0].nature == "suggestion"


def test_complete_eleven_line_log_does_not_prove_upstream_truncation_or_empty_knowledge():
    item, tools, value = setup(
        content="\n".join(["ERROR: install failed"] + ["context"] * 10), source_type="log"
    )
    facts = evidence_facts(tools)
    assert facts.reads[0].reading_complete
    assert facts.reads[0].stored_end == 11
    assert facts.reads[0].source_truncated is None
    assert facts.knowledge_enabled is False
    assert "knowledge_empty" not in facts.model_dump()
    value["boundary_claims"] = [{"kind": "source_truncated", "evidence_id": item["id"]}]
    with pytest.raises(ValueError, match="没有明确采集标记"):
        finish(value, tools)
    value["boundary_claims"][0]["kind"] = "reading_incomplete"
    with pytest.raises(ValueError, match="已读完"):
        finish(value, tools)
    # 只有采集适配器明确记录截断才可声明源材料截断。
    tools.evidence[item["id"]]["capture_truncated"] = True
    value["boundary_claims"][0]["kind"] = "source_truncated"
    assert finish(value, tools).evidence_facts.reads[0].source_truncated is True


def test_partial_read_is_recorded_separately_from_source_truncation():
    item, tools, value = setup(content="first\nsecond\nthird")
    tools.observed[item["id"]] = [(1, 1)]
    value["boundary_claims"] = [{"kind": "reading_incomplete", "evidence_id": item["id"]}]
    state = finish(value, tools).evidence_facts.reads[0]
    assert not state.reading_complete and state.source_truncated is None
    tools.observed[item["id"]] = [(1, 1), (3, 3)]
    assert not evidence_facts(tools).reads[0].reading_complete
    tools.observed[item["id"]].append((2, 2))
    assert evidence_facts(tools).reads[0].reading_complete


def test_no_call_chain_cannot_claim_system_reachability_and_causality_stays_a_hypothesis():
    _, tools, value = setup()
    finding = value["findings"][0]
    finding["reachability"] = "system"
    with pytest.raises(ValueError, match="调用链"):
        finish(value, tools)
    finding.update(
        nature="hypothesis",
        reachability="unknown",
        explanation="调用方可能传入其他所有者的任务；目前没有调用链。",
    )
    result = finish(value, tools)
    assert result.findings[0].nature == "hypothesis"
    assert result.findings[0].semantic_support.status == "not_reviewed"
    finding["unconfirmed_conditions"] = []
    with pytest.raises(ValueError, match="没有确认的条件"):
        finish(value, tools)


def test_historical_null_case_cannot_become_a_current_defect():
    _, tools, value = setup(
        content="历史故障：labels=null 抛出 ValueError。", source_type="document"
    )
    with pytest.raises(ValueError, match="历史资料只能"):
        finish(value, tools)
    finding = value["findings"][0]
    finding.update(
        basis="reference",
        nature="hypothesis",
        explanation="历史故障可作为后续查阅 labels 处理的线索。",
    )
    assert finish(value, tools).findings[0].basis == "reference"
    finding["nature"] = "fact"
    with pytest.raises(ValueError, match="历史线索"):
        finish(value, tools)


def test_current_install_log_cannot_confirm_historical_source_bug_or_old_commit():
    item, tools, value = setup(content="ERROR: No matching distribution found", source_type="log")
    tools.evidence[item["id"]]["version"] = "c" * 40
    with pytest.raises(ValueError, match="没有当前版本"):
        finish(value, tools)
    tools.evidence[item["id"]]["version"] = "a" * 40 + ":attempt-1:job-22"
    tools.metadata["input_version"]["resources"][0]["run_attempt"] = 1
    assert finish(value, tools).citation_check == "passed"
    tools.evidence[item["id"]]["version"] = "a" * 40 + ":attempt-2:job-22"
    with pytest.raises(ValueError, match="没有当前版本"):
        finish(value, tools)


@pytest.mark.parametrize("field", ["quote", "line", "call_chain"])
def test_direct_quotes_and_call_chain_cannot_bypass_read_checks(field):
    _, tools, value = setup(content="return list(tasks)\nunread")
    tools.observed[next(iter(tools.evidence))] = [(1, 1)]
    finding = value["findings"][0]
    if field == "quote":
        finding["direct_evidence"][0]["quote"] = "作者承诺保持权限行为不变"
    elif field == "line":
        finding["direct_evidence"][0]["citation"] = {
            **finding["evidence"][0],
            "start_line": 2,
            "end_line": 2,
        }
    else:
        finding["call_chain"] = [{**finding["evidence"][0], "start_line": 2, "end_line": 2}]
    with pytest.raises(ValueError):
        finish(value, tools)


def test_quote_exists_does_not_mean_it_supports_the_conclusion():
    _, tools, value = setup()
    value["findings"][0]["explanation"] = "错误推断：所有生产入口一定会泄露全部用户数据。"
    result = finish(value, tools)
    assert result.citation_check == "passed"
    assert result.semantic_support.status == "not_reviewed"
    assert result.findings[0].semantic_support.status == "not_reviewed"
    # 这是反例：结构检查不能判定任意自然语言推理正确，不能写成语义检查通过。
    assert "尚未复核" in report_markdown(result, {}, "example")


def test_old_reports_remain_readable_without_inventing_missing_fields():
    item, _, _ = setup()
    legacy = answer(item)
    run = SimpleNamespace(status="succeeded", result={"kind": "analysis_report", "report": legacy})
    parsed = require_report(run)
    assert isinstance(parsed, AnalysisReport)
    assert parsed.model_dump(mode="json")["findings"] == legacy["findings"]
    assert not hasattr(parsed.findings[0], "nature")
    assert "均未记录，显示为未知" in report_markdown(parsed, {}, "old")
    assert isinstance(parse_report(legacy), AnalysisReport)


def test_missing_capture_and_commit_facts_remain_unknown():
    item = evidence()
    tools = ToolGateway("registered", [item], {"input_version": {"repository_commit": "f" * 40}})
    facts = evidence_facts(tools)
    assert facts.collection_complete is None and facts.knowledge_enabled is None
    assert facts.current_versions == []  # 默认仓库提交不能被事后当作本次CI提交。


def test_v2_agent_repairs_a_boundary_violation_and_restores_versioned_report():
    item, tools, good = setup(content="ERROR: install failed", source_type="log")
    tools.observed = {}
    bad = deepcopy(good)
    bad["boundary_claims"] = [{"kind": "source_truncated", "evidence_id": item["id"]}]
    model = ScriptedModel(
        [
            tool_call("read_evidence", {"repo_id": "registered", "evidence_id": item["id"]}),
            ModelReply({"role": "assistant", "content": json.dumps(bad)}),
            ModelReply({"role": "assistant", "content": json.dumps(good)}),
        ]
    )
    config = model_configuration(Settings(_env_file=None, model_provider="fake"))
    config["report_review"]["enabled"] = False  # 本例只验证原有格式修正与恢复。
    config["budget"] = {
        "max_model_calls": 6,
        "max_tool_calls": 12,
        "max_total_tokens": 60000,
        "timeout_seconds": 30,
    }
    runner = AnalysisRunner(model, tools, "pr_review", "审查", config)
    result = runner.run()
    assert result["format_repairs"] == 1
    assert result["report"]["report_version"] == "2"
    assert result["report"]["semantic_support"]["status"] == "not_reviewed"
    assert "没有明确采集标记" in model.calls[-1]["messages"][-1]["content"]
    restored = AnalysisRunner(model, tools, "pr_review", "审查", config)
    restored._restore(json.loads(json.dumps(runner._runtime())))
    assert restored.report == runner.report
    assert evidence_facts(restored.gateway).reads[0].reading_complete


def test_disabled_knowledge_does_not_query_the_index_or_mean_it_is_empty():
    _, tools, _ = setup()

    def forbidden(_):
        pytest.fail("本次未启用知识库，不能访问检索功能")

    tools.knowledge_search = forbidden
    result = tools.execute(
        "search_knowledge", json.dumps({"repo_id": "registered", "query": "owner"})
    )
    assert result["data"]["code"] == "knowledge_disabled"
    assert evidence_facts(tools).knowledge_enabled is False


def test_current_install_log_plus_historical_null_document_is_still_not_current_code_proof():
    current, tools, value = setup(content="ERROR: install failed", source_type="log")
    old = evidence("历史故障：labels=null 抛出 ValueError。", source_type="document")
    tools.evidence[old["id"]] = old
    tools.execute("read_evidence", json.dumps({"repo_id": "registered", "evidence_id": old["id"]}))
    finding = value["findings"][0]
    citation = {"evidence_id": old["id"], "start_line": 1, "end_line": 1}
    finding["evidence"].append(citation)
    finding["direct_evidence"].append(
        {"citation": citation, "quote": old["content"], "observation": "以前曾发生标签故障。"}
    )
    finding.update(claim_type="code_behavior", title="声称本次标签故障复发")
    # 不能通过顺带引用一条当前安装日志，把历史代码故障变成当前代码问题。
    with pytest.raises(ValueError, match="代码判断需要当前代码"):
        finish(value, tools)
    finding.update(basis="reference", nature="hypothesis")
    assert finish(value, tools).findings[0].basis == "reference"
    assert current["id"] in tools.observed


def test_suggestions_and_historical_leads_do_not_count_as_detected_current_defects():
    cases, labels, _ = load_dataset("evals/devflow-v1")
    case = next(c for c in cases if c.case_id == "pr-owner-removed")
    execution = execute_case(case, Settings(_env_file=None, model_provider="fake"))
    report = execution["result"]["report"]
    finding = report["findings"][0]
    finding.update(nature="suggestion", severity="info")
    assert "missed_issue" in {f["tag"] for f in grade(case, labels[case.case_id], execution)}
    finding.update(nature="hypothesis", basis="reference")
    assert "missed_issue" in {f["tag"] for f in grade(case, labels[case.case_id], execution)}


def test_new_direct_citation_is_independently_checked_by_the_evaluator():
    cases, labels, _ = load_dataset("evals/devflow-v1")
    case = next(c for c in cases if c.case_id == "pr-owner-removed")
    execution = execute_case(case, Settings(_env_file=None, model_provider="fake"))
    execution["result"]["report"]["findings"][0]["direct_evidence"][0]["citation"]["end_line"] = 999
    assert "citation" in {f["tag"] for f in grade(case, labels[case.case_id], execution)}


def test_model_cannot_mark_its_own_conclusion_as_reviewed():
    _, _, value = setup()
    value["semantic_support"] = {"status": "supported", "reviewer": "model", "notes": ["自评"]}
    with pytest.raises(ValueError, match="Extra inputs"):
        ReportDraftV2.model_validate(value)


def test_direct_quote_may_use_a_smaller_range_inside_the_findings_citation():
    item, tools, value = setup(content="def list_tasks(tasks, actor_id):\n    return list(tasks)")
    finding = value["findings"][0]
    finding["evidence"][0]["end_line"] = 2
    finding["direct_evidence"] = [
        {
            "citation": {"evidence_id": item["id"], "start_line": 2, "end_line": 2},
            "quote": "    return list(tasks)",
            "observation": "函数直接返回传入的任务。",
        }
    ]
    assert finish(value, tools).citation_check == "passed"
