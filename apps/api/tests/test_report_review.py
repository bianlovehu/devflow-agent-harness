# 文件用途：验证一次复核、一轮补查、预算停止、恢复不重复调用及输出哈希边界。
import json
from copy import deepcopy

import pytest
from devflow.agent import AnalysisRunner, model_configuration
from devflow.config import Settings
from devflow.errors import DomainError
from devflow.model_gateway import ModelError, ModelReply, ScriptedModel, tool_call
from devflow.report_review import (
    BoundedReportReview,
    ReviewDraft,
    digest,
    observed_packets,
    targets,
)
from devflow.report_v2 import ReportDraftV2, finalize_report
from test_report_v2 import setup


def final(value):
    return ModelReply({"role": "assistant", "content": json.dumps(value, ensure_ascii=False)})


def config(**limits):
    value = model_configuration(Settings(_env_file=None, model_provider="fake"))
    value["budget"] = {
        "max_model_calls": 6,
        "max_tool_calls": 12,
        "max_total_tokens": 60000,
        "timeout_seconds": 30,
        **limits,
    }
    return value


def review(value, actions=None, reads=None):
    original = ReportDraftV2.model_validate(value)
    return {
        "decisions": [
            {
                "target": target,
                "action": (actions or {}).get(target, "keep"),
                "category": "missing_context" if target in (actions or {}) else "none",
                "reason": "缺少调用方，系统影响尚未确认。"
                if target in (actions or {})
                else "已读原文支持保留本段。",
                "evidence": [],
                "metadata_evidence": ["reads"],
            }
            for target in targets(original)
        ],
        "reads": reads or [],
    }


def start(item, tools, value, responses, *, configuration=None, journal=None, limit=60):
    tools.observed = {}
    model = ScriptedModel(
        [
            tool_call(
                "read_evidence",
                {"repo_id": "registered", "evidence_id": item["id"], "limit": limit},
            ),
            final(value),
            *responses,
        ]
    )
    journal = {} if journal is None else journal
    runner = AnalysisRunner(
        model,
        tools,
        "pr_review",
        "审查",
        configuration or config(),
        journal_read=journal.get,
        journal_write=lambda k, v: journal.__setitem__(k, deepcopy(v)),
    )
    return runner, model, journal


def test_one_review_is_advice_and_does_not_mark_the_report_correct():
    item, tools, value = setup()
    runner, model, _ = start(item, tools, value, [final(review(value))])
    result = runner.run()
    record = result["report_review"]
    assert len(model.calls) == 3 and record["review_calls"] == 1
    assert record["supplement_rounds"] == record["revision_calls"] == 0
    assert (
        record["input_report_sha256"] == record["output_report_sha256"] == digest(result["report"])
    )
    assert result["report"]["semantic_support"]["status"] == "not_reviewed"
    assert record["deterministic"]["status"] == "passed"
    assert model.calls[-1]["tools"] == []


@pytest.mark.parametrize("mutation", ["identity", "version", "unread", "metadata", "truncation"])
def test_deterministic_failure_prevents_review_spending(mutation):
    item, tools, value = setup()
    report = finalize_report(ReportDraftV2.model_validate(value), tools, "pr_review")
    if mutation == "identity":
        tools.evidence[item["id"]]["artifact_id"] = "wrong"
    elif mutation == "version":
        tools.evidence[item["id"]]["version"] = "b" * 40
    elif mutation == "unread":
        tools.observed = {}
    elif mutation == "metadata":
        report.evidence_facts.knowledge_enabled = True
    else:
        from devflow.report_v2 import BoundaryClaim

        report.boundary_claims = [BoundaryClaim(kind="source_truncated", evidence_id=item["id"])]
    model = ScriptedModel([])
    runner = AnalysisRunner(model, tools, "pr_review", "审查", config())
    runner.report = report
    with pytest.raises(DomainError, match="不一致"):
        BoundedReportReview(runner).run()
    assert not model.calls and runner.review_state["deterministic"]["status"] == "failed"


def test_reviewer_never_sees_unread_lines():
    item, tools, _ = setup(content="visible\nsecret unread")
    tools.observed[item["id"]] = [(1, 1)]
    assert observed_packets(tools)[0]["lines"] == [{"line": 1, "text": "visible"}]
    assert "secret unread" not in json.dumps(observed_packets(tools))


def test_downgrade_survives_no_budget_for_revision():
    item, tools, value = setup()
    runner, model, _ = start(
        item,
        tools,
        value,
        [final(review(value, {"finding:0": "downgrade"}))],
        configuration=config(max_model_calls=3),
    )
    result = runner.run()
    record = result["report_review"]
    assert result["report"]["findings"][0]["nature"] == "hypothesis"
    assert record["revision_calls"] == 0 and len(model.calls) == 3
    assert record["input_report_sha256"] != record["output_report_sha256"]
    assert result["report"]["semantic_support"]["status"] == "not_reviewed"


def test_removal_is_applied_even_if_editor_reintroduces_the_old_finding():
    item, tools, value = setup()
    runner, _, _ = start(
        item,
        tools,
        value,
        [
            final(review(value, {"finding:0": "remove"})),
            final({"report": value, "finding_origins": [0]}),
        ],
    )
    result = runner.run()
    assert result["report"]["findings"] == []
    assert result["report_review"]["revision_calls"] == 1


def test_summary_is_synchronized_when_a_finding_changes():
    item, tools, value = setup()
    value["summary"] = "已有用户数据泄露。"
    changed = deepcopy(value)
    changed["summary"] = "局部过滤发生变化，是否影响用户未知。"
    runner, _, _ = start(
        item,
        tools,
        value,
        [
            final(review(value, {"finding:0": "downgrade"})),
            final({"report": changed, "finding_origins": [0]}),
        ],
    )
    result = runner.run()
    assert result["report"]["summary"] == changed["summary"]
    assert result["report_review"]["output_report_sha256"] == digest(result["report"])


def test_only_one_supplement_round_and_one_revision_with_real_new_lines():
    item, tools, value = setup(content="first\nsecond\nthird")
    request = {
        "tool": "read_evidence",
        "arguments": {
            "repo_id": "registered",
            "evidence_id": item["id"],
            "start_line": 2,
            "limit": 2,
        },
        "reason": "核查后续内容。",
    }
    changed = deepcopy(value)
    changed["findings"][0]["explanation"] = "补查后保留局部观察，系统影响未知。"
    runner, model, _ = start(
        item,
        tools,
        value,
        [
            final(review(value, {"finding:0": "need_evidence"}, [request])),
            final({"report": changed, "finding_origins": [0]}),
        ],
        limit=1,
    )
    result = runner.run()
    record = result["report_review"]
    assert record["supplement_rounds"] == record["review_calls"] == record["revision_calls"] == 1
    assert record["supplement"]["new_evidence"] is True
    assert len(record["supplement"]["results"]) == 1 and runner.tool_calls == 2
    assert len(model.calls) == 4 and record["output_report_sha256"] == digest(result["report"])


def test_duplicate_read_does_not_pretend_to_fill_a_gap():
    item, tools, value = setup()
    request = {
        "tool": "read_evidence",
        "arguments": {"repo_id": "registered", "evidence_id": item["id"], "limit": 60},
        "reason": "重复读取不应被当成新证据。",
    }
    runner, _, _ = start(
        item,
        tools,
        value,
        [
            final(review(value, {"finding:0": "need_evidence"}, [request])),
            final({"report": value, "finding_origins": [0]}),
        ],
    )
    result = runner.run()
    assert result["report_review"]["supplement"]["new_evidence"] is False
    assert result["report"]["findings"][0]["nature"] == "hypothesis"


@pytest.mark.parametrize(
    "bad",
    ["score", "missing_target", "unknown_tool", "cross_repo", "unread_citation", "too_many_reads"],
)
def test_invalid_review_has_no_retry_or_uncontrolled_tool_access(bad):
    item, tools, value = setup(content="first\nunread")
    payload = review(value, {"finding:0": "need_evidence"})
    request = {
        "tool": "read_evidence",
        "arguments": {"repo_id": "registered", "evidence_id": item["id"]},
        "reason": "补查。",
    }
    if bad == "score":
        payload["score"] = 0.99
    elif bad == "missing_target":
        payload["decisions"].pop()
    elif bad == "unknown_tool":
        payload["reads"] = [{**request, "tool": "exec_shell"}]
    elif bad == "cross_repo":
        payload["reads"] = [{**request, "arguments": {**request["arguments"], "repo_id": "other"}}]
    elif bad == "unread_citation":
        payload["decisions"][0]["evidence"] = [
            {"evidence_id": item["id"], "start_line": 2, "end_line": 2}
        ]
    else:
        payload["reads"] = [request] * 4
    runner, model, _ = start(item, tools, value, [final(payload)], limit=1)
    result = runner.run()
    assert result["report_review"]["status"] == "review_unavailable"
    assert len(model.calls) == 3 and runner.tool_calls == 1
    assert result["report"]["semantic_support"]["status"] == "not_reviewed"


def test_insufficient_task_budget_skips_review_and_keeps_the_gap_visible():
    item, tools, value = setup()
    runner, model, _ = start(item, tools, value, [], configuration=config(max_model_calls=2))
    result = runner.run()
    assert len(model.calls) == 2 and result["report_review"]["review_calls"] == 0
    assert result["report_review"]["status"] == "skipped_budget"
    assert any("复核未完成" in s for s in result["report"]["unconfirmed"])


@pytest.mark.parametrize(
    "error",
    [
        DomainError(402, "cost_budget_exceeded", "额度不足"),
        ModelError("model_network_error", "网络失败"),
    ],
)
def test_optional_call_failure_does_not_destroy_the_original_valid_report(error):
    item, tools, value = setup()
    runner, model, _ = start(item, tools, value, [error])
    result = runner.run()
    assert result["kind"] == "analysis_report" and len(model.calls) == 3
    assert result["report_review"]["review_calls"] == 1
    assert result["report"]["findings"]


def test_budget_exhaustion_does_not_read_or_iterate_without_revision_capacity():
    item, tools, value = setup(content="first\nsecond")
    request = {
        "tool": "read_evidence",
        "arguments": {"repo_id": "registered", "evidence_id": item["id"], "start_line": 2},
        "reason": "读后续。",
    }
    runner, model, _ = start(
        item,
        tools,
        value,
        [final(review(value, {"finding:0": "need_evidence"}, [request]))],
        configuration=config(max_model_calls=3),
        limit=1,
    )
    result = runner.run()
    assert runner.tool_calls == 1 and len(model.calls) == 3
    assert result["report_review"]["supplement_rounds"] == 0
    assert result["report"]["findings"][0]["nature"] == "hypothesis"


@pytest.mark.parametrize("paid_response", [False, True])
def test_crash_recovery_never_repeats_review_request(paid_response):
    class Crash(Exception):
        pass

    item, tools, value = setup()
    journal = {}
    runner, model, _ = start(
        item, tools, value, [final(review(value)) if paid_response else Crash()], journal=journal
    )
    if paid_response:

        def write(key, snapshot):
            journal[key] = deepcopy(snapshot)
            calls = snapshot.get("trace", {}).get("calls", []) if key == "runtime" else []
            if (
                calls
                and calls[-1].get("phase") == "review"
                and "response" in calls[-1]
                and not snapshot["review_state"].get("decisions")
            ):
                raise Crash()

        runner.journal_write = write
    with pytest.raises(Crash):
        runner.run()
    resumed_model = ScriptedModel([])
    resumed = AnalysisRunner(
        resumed_model,
        tools,
        "pr_review",
        "审查",
        runner.configuration,
        journal_read=journal.get,
        journal_write=lambda k, v: journal.__setitem__(k, deepcopy(v)),
    )
    result = resumed.run()
    assert not resumed_model.calls and result["report_review"]["review_calls"] == 1
    assert result["report_review"]["status"] == (
        "completed" if paid_response else "review_unavailable"
    )


def test_old_configurations_do_not_gain_a_new_paid_stage():
    item, tools, value = setup()
    c = config()
    c.pop("report_review")
    runner, model, _ = start(item, tools, value, [], configuration=c)
    assert "report_review" not in runner.run() and len(model.calls) == 2


def test_only_four_actions_and_no_self_scores_are_accepted():
    item, _, value = setup()
    payload = review(value)
    payload["decisions"][0]["action"] = "approved_correct"
    with pytest.raises(ValueError):
        ReviewDraft.model_validate(payload)
