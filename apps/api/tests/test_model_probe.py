# 文件用途：用模拟响应验证模型探测次数、用量输出和密钥脱敏。
import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from devflow.config import Settings
from devflow.model_probe import probe_deepseek


def test_probe_without_key_makes_no_request():
    with patch("devflow.model_probe.urlopen") as request:
        result = probe_deepseek(Settings(_env_file=None, deepseek_api_key=""))
    assert result["status"] == "not_configured"
    request.assert_not_called()


def test_probe_makes_one_bounded_request_and_returns_usage_only():
    settings = Settings(_env_file=None, deepseek_api_key="private-test-value")
    response = MagicMock()
    response.__enter__.return_value = io.BytesIO(
        json.dumps(
            {
                "model": "deepseek-flash",
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
            }
        ).encode()
    )
    with patch("devflow.model_probe.urlopen", return_value=response) as request:
        result = probe_deepseek(settings)
    assert result["status"] == "ok"
    assert result["total_tokens"] == 10
    request.assert_called_once()
    payload = json.loads(request.call_args.args[0].data)
    assert payload["max_tokens"] == 8
    assert payload["thinking"]["type"] == "disabled"
    assert "private-test-value" not in json.dumps(result)


def test_auth_error_is_sanitized_and_not_retried():
    settings = Settings(_env_file=None, deepseek_api_key="private-test-value")
    failure = HTTPError("https://api.deepseek.com/chat/completions", 401, "secret", {}, None)
    with patch("devflow.model_probe.urlopen", side_effect=failure) as request:
        result = probe_deepseek(settings)
    assert result["http_status"] == 401
    assert "private-test-value" not in json.dumps(result)
    assert "secret" not in json.dumps(result)
    request.assert_called_once()
