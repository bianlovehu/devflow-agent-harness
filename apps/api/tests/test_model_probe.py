# 文件用途：验证探针通过统一网关、显式隔离账本，且不泄露密钥或自动重试。
import io
import json
from urllib.error import HTTPError

from budget_samples import StubLedger
from devflow.config import Settings
from devflow.model_probe import probe_deepseek


class Opener:
    calls = 0

    def __init__(self, failure=None):
        self.failure = failure

    def open(self, request, timeout):
        self.calls += 1
        self.request = request
        if self.failure:
            raise self.failure
        return io.BytesIO(
            json.dumps(
                {
                    "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
                }
            ).encode()
        )


def test_probe_without_key_makes_no_request():
    opener = Opener()
    result = probe_deepseek(
        Settings(_env_file=None, deepseek_api_key=""), opener=opener, ledger=StubLedger()
    )
    assert result["status"] == "not_configured" and opener.calls == 0


def test_probe_makes_one_bounded_request_and_returns_usage_only():
    opener, ledger = Opener(), StubLedger()
    result = probe_deepseek(
        Settings(_env_file=None, deepseek_api_key="private-test-value"),
        opener=opener,
        ledger=ledger,
    )
    assert result["status"] == "ok" and result["total_tokens"] == 10
    assert opener.calls == 1 and ledger.reservations[0]["purpose"] == "probe"
    payload = json.loads(opener.request.data)
    assert payload["max_tokens"] == 16 and payload["thinking"]["type"] == "disabled"
    assert "private-test-value" not in json.dumps(result)


def test_auth_error_is_sanitized_and_not_retried():
    opener = Opener(HTTPError("https://api.deepseek.com/chat/completions", 401, "secret", {}, None))
    ledger = StubLedger()
    result = probe_deepseek(
        Settings(_env_file=None, deepseek_api_key="private-test-value"),
        opener=opener,
        ledger=ledger,
    )
    assert result["code"] == "model_auth_error" and opener.calls == 1
    assert "private-test-value" not in json.dumps(result) and "secret" not in json.dumps(result)
    assert ledger.finished[0]["usage"] is None and ledger.finished[0]["sent"]
