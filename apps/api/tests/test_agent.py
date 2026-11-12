# 文件用途：验证工具权限、引用、模型错误、预算与 LangGraph 的真实执行路径。
import io
import json
from urllib.error import HTTPError
from uuid import uuid4

import pytest
from budget_samples import StubLedger
from devflow.agent import AnalysisRunner, model_configuration
from devflow.config import Settings
from devflow.errors import DomainError
from devflow.fake_model import FixtureModel
from devflow.model_gateway import (
    DeepSeekModel,
    ModelError,
    ModelReply,
    ScriptedModel,
    Usage,
    tool_call,
)
from devflow.reports import AnalysisReport, report_markdown
from devflow.tool_gateway import ToolGateway, log_windows


def evidence(content="return list(tasks)\n", source_type="file", **updates):
    return {
        "id": str(uuid4()),
        "artifact_id": str(uuid4()),
        "source_type": source_type,
        "path": "service.py",
        "version": "a" * 40,
        "start_line": 1,
        "end_line": max(1, len(content.splitlines())),
        "content": content,
        **updates,
    }


def gateway(*items):
    return ToolGateway("registered", list(items or [evidence()]), {})


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_old_document_trailing_newline_metadata_does_not_crash_reread(ending):
    item = evidence("owner policy" + ending, source_type="document", end_line=2)
    tools = gateway(item)
    reply = tools.execute(
        "read_evidence",
        json.dumps({"repo_id": "registered", "evidence_id": item["id"], "limit": 20}),
    )
    assert reply["ok"]
    assert reply["data"]["lines"] == [{"line": 1, "text": "owner policy"}]
    assert reply["data"]["end_line"] == 1 and reply["data"]["next_line"] is None
    invalid = tools.execute(
        "read_evidence",
        json.dumps({"repo_id": "registered", "evidence_id": item["id"], "start_line": 2}),
    )
    assert invalid["error"]["code"] == "invalid_line_range"


def config(**budget):
    return {
        **model_configuration(Settings(_env_file=None, model_provider="fake")),
        # 此文件保留旧版报告与旧任务恢复的回归，新版分类另见 test_report_v2.py。
        "report_version": "1",
        "report_schema": AnalysisReport.model_json_schema(),
        "budget": {
            "max_model_calls": 6,
            "max_tool_calls": 12,
            "max_total_tokens": 60000,
            "timeout_seconds": 30,
            **budget,
        },
    }


def answer(item, **updates):
    return {
        "task_type": "pr_review",
        "summary": "权限边界需要核查",
        "findings": [
            {
                "title": "未筛选任务所有者",
                "severity": "high",
                "explanation": "直接返回全部任务。",
                "evidence": [{"evidence_id": item["id"], "start_line": 1, "end_line": 1}],
                "suggestion": "恢复所有者筛选。",
            }
        ],
        "verification_steps": ["添加跨用户回归测试。"],
        "suggestions": [],
        "unconfirmed": [],
        "scope": ["当前固定文件。"],
        **updates,
    }


def final(value):
    return ModelReply({"role": "assistant", "content": json.dumps(value)})


@pytest.mark.parametrize(
    "name,args,code",
    [
        ("exec_shell", {}, "unknown_tool"),
        ("get_pr", {"repo_id": "other"}, "tool_repository_denied"),
        ("get_pr", {"repo_id": "registered", "unexpected": True}, "invalid_tool_arguments"),
        ("get_pr", {"repo_id": "registered", "limit": 99999}, "invalid_tool_arguments"),
        (
            "read_file",
            {"repo_id": "registered", "path": "../secret", "commit": "a" * 40},
            "invalid_file_path",
        ),
        (
            "read_file",
            {"repo_id": "registered", "path": "service.py", "commit": "b" * 40},
            "tool_evidence_not_found",
        ),
    ],
)
def test_tool_gateway_enforces_server_scope(name, args, code):
    result = gateway().execute(name, json.dumps(args))
    assert result["ok"] is False and result["error"]["code"] == code


def test_tool_paging_duplicate_detection_and_exact_observed_ranges():
    item = evidence("one\ntwo\nthree\n")
    tools = gateway(item)
    args = json.dumps({"repo_id": "registered", "evidence_id": item["id"], "limit": 2})
    result = tools.execute("read_evidence", args)
    assert result["data"]["next_line"] == 3
    assert result["data"]["lines"][1] == {"line": 2, "text": "two"}
    assert tools.execute("read_evidence", args)["duplicate"]
    assert tools.observed[item["id"]] == [(1, 2), (1, 2)]


def test_long_line_and_metadata_have_explicit_limits():
    item = evidence("x" * 13000)
    tools = gateway(item)
    result = tools.execute(
        "read_evidence", json.dumps({"repo_id": "registered", "evidence_id": item["id"]})
    )
    assert result["error"]["code"] == "tool_line_too_long"
    assert not tools.observed
    tools.metadata = {"huge": "x" * 13000}
    assert (
        tools.execute("get_pr", '{"repo_id":"registered"}')["error"]["code"]
        == "tool_result_too_large"
    )


def test_ci_error_blocks_preserve_original_lines_and_full_pointer():
    item = evidence("ok\ninstall\nERROR: No matching distribution found\nexit code 1\n", "log")
    tools = gateway(item)
    result = tools.execute(
        "read_log", json.dumps({"repo_id": "registered", "evidence_id": item["id"]})
    )["data"]
    assert result["full_artifact_id"] == item["artifact_id"]
    assert result["fragments"][0]["lines"][2]["line"] == 3
    assert log_windows(item["content"]) == [(1, 4)]


def test_langgraph_reads_tool_then_validates_report_and_usage():
    item = evidence()
    model = ScriptedModel(
        [
            tool_call("read_evidence", {"repo_id": "registered", "evidence_id": item["id"]}),
            ModelReply(
                final(answer(item)).message,
                Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            ),
        ]
    )
    result = AnalysisRunner(model, gateway(item), "pr_review", "审查", config()).run()
    assert result["report"]["findings"][0]["evidence"][0]["evidence_id"] == item["id"]
    assert result["model_calls"] == 2 and result["usage"]["total_tokens"] == 30
    assert model.calls[1]["messages"][-1]["role"] == "tool"


@pytest.mark.parametrize("bad_citation", ["unknown", "out_of_range", "unread"])
def test_invalid_citations_never_enter_final_report_and_repair_once(bad_citation):
    item, unread = evidence(), evidence()
    value = answer(unread if bad_citation == "unread" else item)
    citation = value["findings"][0]["evidence"][0]
    if bad_citation == "unknown":
        citation["evidence_id"] = str(uuid4())
    elif bad_citation == "out_of_range":
        citation["end_line"] = 999
    model = ScriptedModel(
        [
            tool_call("read_evidence", {"repo_id": "registered", "evidence_id": item["id"]}),
            final(value),
            final(value),
        ]
    )
    runner = AnalysisRunner(model, gateway(item, unread), "pr_review", "审查", config())
    with pytest.raises(ModelError) as error:
        runner.run()
    assert error.value.code == "model_format_error" and len(model.calls) == 3
    assert runner.repairs == 1


def test_evidence_insufficient_can_return_empty_findings_after_one_repair():
    item = evidence()
    model = ScriptedModel(
        [
            tool_call("get_pr", {"repo_id": "registered"}),
            final(answer(item)),
            final(answer(item, findings=[], unconfirmed=["只取得目录，没有正文。"])),
        ]
    )
    result = AnalysisRunner(model, gateway(item), "pr_review", "审查", config()).run()
    assert not result["report"]["findings"] and result["format_repairs"] == 1


@pytest.mark.parametrize(
    "budget", [{"max_model_calls": 1}, {"max_tool_calls": 1}, {"max_total_tokens": 1000}]
)
def test_business_budgets_stop_before_further_work(budget):
    item = evidence()
    reply = tool_call("get_pr", {"repo_id": "registered"})
    model = ScriptedModel([reply, reply, reply])
    with pytest.raises(DomainError) as error:
        AnalysisRunner(model, gateway(item), "pr_review", "审查", config(**budget)).run()
    assert error.value.code == "budget_exceeded"


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "model_auth_error"),
        (402, "model_balance_error"),
        (429, "model_rate_limited"),
        (500, "model_network_error"),
    ],
)
def test_model_http_errors_are_classified_and_never_retried(status, code):
    class Opener:
        calls = 0

        def open(self, *args, **kwargs):
            self.calls += 1
            raise HTTPError(
                "https://api.deepseek.com", status, "secret-error", {}, io.BytesIO(b"secret")
            )

    opener = Opener()
    model = DeepSeekModel(
        Settings(_env_file=None, model_provider="deepseek", deepseek_api_key="private"),
        opener=opener,
        ledger=StubLedger(),
    )
    with pytest.raises(ModelError) as error:
        model.complete([], [])
    assert error.value.code == code and opener.calls == 1
    assert "private" not in error.value.message and "secret" not in error.value.message


def test_aliyun_uses_selected_model_endpoint_and_non_thinking_payload():
    class Opener:
        def open(self, request, timeout):
            self.request = request
            self.payload = json.loads(request.data)
            return io.BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {"finish_reason": "stop", "message": {"content": '{"ok":true}'}}
                        ],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                    }
                ).encode()
            )

    opener = Opener()
    settings = Settings(
        _env_file=None,
        model_provider="aliyun",
        dashscope_api_key="private",
        dashscope_base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    model = DeepSeekModel(settings, opener=opener, ledger=StubLedger())
    assert model.complete([], []).usage.total_tokens == 5
    assert opener.request.full_url == settings.dashscope_base_url + "/chat/completions"
    assert opener.payload["model"] == "deepseek-v4.1-flash"
    assert opener.payload["enable_thinking"] is False and "thinking" not in opener.payload


def test_aliyun_rejects_untrusted_endpoint_before_sending_secret():
    settings = Settings(
        _env_file=None,
        model_provider="aliyun",
        dashscope_api_key="private",
        dashscope_base_url="https://evil.example/compatible-mode/v1",
    )
    with pytest.raises(ModelError) as error:
        DeepSeekModel(settings).complete([], [])
    assert error.value.code == "model_configuration_error"


def test_fake_demo_uses_visible_evidence_and_markdown_escapes_untrusted_html():
    item = evidence()
    result = AnalysisRunner(FixtureModel(), gateway(item), "pr_review", "审查", config()).run()
    assert result["provider"] == "fake" and result["report"]["findings"]
    report = AnalysisReport.model_validate(
        {**result["report"], "summary": "<script>alert(1)</script> [x](https://evil.example)"}
    )
    text = report_markdown(report, result, "run")
    assert "<script>" not in text and "[x]" not in text
    assert "\r\n" in text and "分析建议" in text


@pytest.mark.parametrize("message", [[], "invalid", 7, None])
def test_malformed_model_message_is_classified_without_internal_error(message):
    class Opener:
        def open(self, *args, **kwargs):
            return io.BytesIO(
                json.dumps(
                    {
                        "choices": [{"finish_reason": "stop", "message": message}],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                    }
                ).encode()
            )

    model = DeepSeekModel(
        Settings(_env_file=None, model_provider="deepseek", deepseek_api_key="private"),
        opener=Opener(),
        ledger=StubLedger(),
    )
    with pytest.raises(ModelError) as error:
        model.complete([], [])
    assert error.value.code == "model_format_error"
    assert error.value.usage.total_tokens == 5


@pytest.mark.parametrize("usage", [{}, {"prompt_tokens": 3, "completion_tokens": 2}])
def test_real_model_never_silently_defaults_missing_usage_to_zero(usage):
    class Opener:
        def open(self, *args, **kwargs):
            return io.BytesIO(
                json.dumps(
                    {
                        "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                        "usage": usage,
                    }
                ).encode()
            )

    model = DeepSeekModel(
        Settings(_env_file=None, model_provider="deepseek", deepseek_api_key="private"),
        opener=Opener(),
        ledger=StubLedger(),
    )
    with pytest.raises(ModelError) as error:
        model.complete([], [])
    assert error.value.code == "model_format_error"


def test_log_error_pagination_reaches_errors_after_first_four_blocks():
    content = "\n".join(f"ERROR {i}" if i % 12 == 0 else "ok" for i in range(100))
    item = evidence(content, "log")
    tools = gateway(item)
    cursor, seen = 1, set()
    for _ in range(15):
        result = tools.execute(
            "read_log",
            json.dumps(
                {
                    "repo_id": "registered",
                    "evidence_id": item["id"],
                    "start_line": cursor,
                }
            ),
        )["data"]
        for fragment in result["fragments"]:
            seen.update(line["line"] for line in fragment["lines"] if "ERROR" in line["text"])
        next_line = result["next_line"]
        if next_line is None:
            break
        assert next_line > cursor
        cursor = next_line
    assert seen == set(range(1, 101, 12))


def test_log_error_detection_uses_same_line_numbers_as_evidence_reader():
    item = evidence("prefix\u2028ERROR: failed\nlast", "log", end_line=2)
    assert log_windows(item["content"], context=0) == [(1, 1)]
    tools = gateway(item)
    result = tools.execute(
        "read_log",
        json.dumps(
            {
                "repo_id": "registered",
                "evidence_id": item["id"],
            }
        ),
    )
    assert result["ok"]
    assert result["data"]["fragments"][0]["lines"][0] == {
        "line": 1,
        "text": "prefix\u2028ERROR: failed",
    }


def test_format_error_usage_is_recorded_and_counts_before_any_repair():
    usage = Usage(prompt_tokens=30000, completion_tokens=31000, total_tokens=61000)
    model = ScriptedModel([ModelError("model_format_error", "invalid", usage=usage)])
    runner = AnalysisRunner(model, gateway(), "pr_review", "审查", config())
    with pytest.raises(DomainError) as error:
        runner.run()
    assert error.value.code == "budget_exceeded"
    assert runner.total_tokens == 61000 and len(model.calls) == 1
    assert runner.trace["calls"][0]["usage"] == usage.model_dump()


def test_format_repair_keeps_already_billed_usage():
    item = evidence()
    model = ScriptedModel(
        [
            tool_call("read_evidence", {"repo_id": "registered", "evidence_id": item["id"]}),
            ModelError(
                "model_format_error",
                "invalid",
                usage=Usage(
                    prompt_tokens=10,
                    completion_tokens=20,
                    total_tokens=30,
                ),
            ),
            final(answer(item)),
        ]
    )
    runner = AnalysisRunner(model, gateway(item), "pr_review", "审查", config())
    result = runner.run()
    assert result["format_repairs"] == 1 and result["usage"]["total_tokens"] == 30
    assert len(model.calls) == 3


def test_model_requests_use_remaining_task_time_instead_of_fresh_budget():
    item = evidence()
    model = ScriptedModel(
        [
            tool_call("read_evidence", {"repo_id": "registered", "evidence_id": item["id"]}),
            final(answer(item)),
        ]
    )
    AnalysisRunner(model, gateway(item), "pr_review", "审查", config(), timeout_seconds=2).run()
    assert all(0 < call["timeout"] <= 2 for call in model.calls)


def test_expired_remaining_task_time_stops_before_model_request():
    model = ScriptedModel([])
    with pytest.raises(DomainError) as error:
        AnalysisRunner(model, gateway(), "pr_review", "审查", config(), timeout_seconds=0).run()
    assert error.value.code == "timeout" and not model.calls
