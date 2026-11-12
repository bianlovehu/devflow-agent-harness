# 文件用途：验证新限额、工具语义指纹、连续循环停止和恢复后的幂等计数。
from copy import deepcopy

import pytest
from budget_samples import StubLedger
from devflow.agent import AnalysisRunner
from devflow.config import Settings
from devflow.errors import DomainError
from devflow.model_gateway import DeepSeekModel, ScriptedModel, tool_call
from devflow.runtime_policy import cost, pricing
from devflow.tool_gateway import call_fingerprint
from devflow.workflow_contracts import RunBudget
from pydantic import ValidationError
from test_agent import answer, config, evidence, final, gateway


def test_new_token_defaults_and_client_hard_limits():
    settings = Settings(_env_file=None)
    assert (settings.context_input_tokens, settings.model_max_output_tokens) == (120000, 20000)
    assert RunBudget().max_total_tokens == 600000
    for values in [
        {"max_model_calls": 7},
        {"max_tool_calls": 13},
        {"max_total_tokens": 600001},
        {"timeout_seconds": 601},
    ]:
        with pytest.raises(ValidationError):
            RunBudget(**values)
    for values in [
        {"context_input_tokens": 120001},
        {"model_max_output_tokens": 20001},
        {"budget_warning_cny": 190},
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)
    quote = pricing(
        "aliyun", "deepseek-v4.1-flash", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert str(cost(120000, 20000, quote)) == "0.40000000"
    with pytest.raises(DomainError) as error:
        pricing(
            "aliyun",
            "deepseek-v4.1-flash",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
    assert error.value.code == "pricing_not_configured"


def test_fingerprint_normalizes_order_whitespace_defaults_and_invalid_json():
    first = call_fingerprint("get_pr", '{"repo_id":"registered"}')
    assert first == call_fingerprint(
        "get_pr", '{ "limit":10, "repo_id": "registered", "offset":0 }'
    )
    assert first != call_fingerprint("get_pr", '{"repo_id":"registered","offset":10}')
    assert call_fingerprint("unknown", '{"a":1,"b":2}') == call_fingerprint(
        "unknown", '{"b":2,"a":1}'
    )
    assert call_fingerprint("get_pr", "broken") == call_fingerprint("get_pr", "broken")


@pytest.mark.parametrize("name", ["get_pr", "create_comment"])
def test_third_identical_call_stops_before_execution_and_next_model(name):
    model = ScriptedModel([tool_call(name, {"repo_id": "registered"}, str(i)) for i in range(4)])
    tools = gateway()
    events = []
    tools.emit = lambda name, value: events.append(name)
    runner = AnalysisRunner(model, tools, "pr_review", "分析", config())
    with pytest.raises(DomainError) as error:
        runner.run()
    assert error.value.code == "loop_detected"
    assert len(model.calls) == 3 and runner.tool_calls == 2
    assert events.count("tool.started") == 2


def test_batch_calls_are_checked_in_order_and_different_queries_reset_count():
    calls = [
        tool_call("get_pr", {"repo_id": "registered"}, str(i)).message["tool_calls"][0]
        for i in range(3)
    ]
    runner = AnalysisRunner(ScriptedModel([]), gateway(), "pr_review", "分析", config())
    with pytest.raises(DomainError):
        runner.execute_tools({"messages": [], "calls": calls})
    assert runner.tool_calls == 2
    item = evidence()
    model = ScriptedModel(
        [
            tool_call("get_pr", {"repo_id": "registered"}, "a"),
            tool_call("get_ci", {"repo_id": "registered"}, "b"),
            tool_call("get_pr", {"repo_id": "registered", "offset": 1}, "c"),
            final(answer(item, findings=[])),
        ]
    )
    assert (
        AnalysisRunner(model, gateway(item), "pr_review", "分析", config()).run()["tool_calls"] == 3
    )


def test_loop_counter_survives_restart_and_completed_replay_does_not_increment():
    journal = {}

    def runner():
        return AnalysisRunner(
            ScriptedModel([]),
            gateway(),
            "pr_review",
            "分析",
            config(),
            journal_read=lambda key: deepcopy(journal.get(key)),
            journal_write=lambda key, value: journal.update({key: deepcopy(value)}),
        )

    states = [
        {
            "messages": [],
            "calls": tool_call("get_pr", {"repo_id": "registered"}, str(i)).message["tool_calls"],
        }
        for i in range(3)
    ]
    original = runner()
    original.execute_tools(states[0])
    original.execute_tools(states[1])
    recovered = runner()
    recovered.execute_tools(states[1])
    assert recovered.loop_policy["count"] == 2 and recovered.tool_calls == 2
    with pytest.raises(DomainError) as error:
        recovered.execute_tools(states[2])
    assert error.value.code == "loop_detected"


def test_gateway_rejects_oversized_input_output_before_reservation():
    ledger = StubLedger()
    model = DeepSeekModel(
        Settings(
            _env_file=None,
            model_provider="aliyun",
            dashscope_api_key="private",
            dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        ledger=ledger,
    )
    for messages, maximum in [([], 20001), ([{"role": "user", "content": "中" * 41000}], 20000)]:
        with pytest.raises(DomainError) as error:
            model.complete(messages, [], max_tokens=maximum)
        assert error.value.code == "budget_exceeded"
    assert not ledger.reservations
