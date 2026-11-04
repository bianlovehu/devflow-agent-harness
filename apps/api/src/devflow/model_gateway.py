# 文件用途：统一 DeepSeek 消息、工具调用、超时、响应校验及用量；不自动重试模型请求。
import json
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from devflow.errors import DomainError


class Usage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


@dataclass
class ModelReply:
    message: dict
    usage: Usage = field(default_factory=Usage)


class ModelError(DomainError):
    def __init__(self, code, message, *, usage=None):
        super().__init__(502, code, message)
        self.usage = usage


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeepSeekModel:
    provider = "deepseek"

    def __init__(self, settings, *, opener=None):
        self.settings = settings
        self.provider = settings.model_provider
        self.name = (
            settings.dashscope_model if self.provider == "aliyun" else settings.deepseek_model
        )
        self.opener = opener or build_opener(NoRedirect())

    def complete(self, messages, tools, *, max_tokens=3000, timeout=None):
        aliyun = self.provider == "aliyun"
        key = (
            (self.settings.dashscope_api_key if aliyun else self.settings.deepseek_api_key)
            .get_secret_value()
            .strip()
        )
        if not key:
            raise ModelError("model_auth_error", "请在服务端配置模型供应商 API Key")
        endpoint = "https://api.deepseek.com/chat/completions"
        if aliyun:
            base = self.settings.dashscope_base_url.rstrip("/")
            parsed = urlsplit(base)
            if (
                parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or parsed.port
                or parsed.query
                or parsed.fragment
                or not (
                    parsed.hostname == "dashscope.aliyuncs.com"
                    or (parsed.hostname or "").endswith(".maas.aliyuncs.com")
                    or parsed.hostname
                    in {"dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"}
                )
                or parsed.path != "/compatible-mode/v1"
            ):
                raise ModelError("model_configuration_error", "请配置阿里云官方兼容模式 Base URL")
            endpoint = base + "/chat/completions"
        payload = {
            "model": self.name,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
        }
        if aliyun:
            payload["enable_thinking"] = False
        else:
            payload["thinking"] = {"type": "disabled"}
        if tools:
            payload["tools"] = tools
        else:
            payload["response_format"] = {"type": "json_object"}
        request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        usage = None
        try:
            with self.opener.open(
                request, timeout=min(timeout or 120, self.settings.model_timeout_seconds)
            ) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ModelError("model_format_error", "模型响应超过 1 MiB 限制")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("invalid response")
            # 真实调用必须提供完整用量；格式失败的已发生用量仍需计入任务预算。
            usage = Usage.model_validate({key: data["usage"][key] for key in Usage.model_fields})
            if usage.total_tokens < usage.prompt_tokens + usage.completion_tokens:
                usage = usage.model_copy(
                    update={"total_tokens": usage.prompt_tokens + usage.completion_tokens}
                )
                raise ValueError("inconsistent usage")
            if not isinstance(data["choices"], list):
                raise ValueError("invalid choices")
            choice = data["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError("invalid choice")
            if choice["finish_reason"] not in {"stop", "tool_calls"}:
                raise ModelError("model_format_error", "模型输出未完整结束", usage=usage)
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError("invalid message")
            calls = message.get("tool_calls")
            if calls is None:
                calls = []
            if not isinstance(calls, list) or len(calls) > 12:
                raise ValueError("invalid tool calls")
            for call in calls:
                if (
                    not isinstance(call, dict)
                    or call["type"] != "function"
                    or not isinstance(call["function"], dict)
                    or not isinstance(call["id"], str)
                    or not isinstance(call["function"]["name"], str)
                    or not isinstance(call["function"]["arguments"], str)
                ):
                    raise ValueError("invalid function")
            if len({call["id"] for call in calls}) != len(calls):
                raise ValueError("duplicate tool call id")
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError("invalid content")
            if not calls and not content:
                raise ValueError("empty content")
            clean = {"role": "assistant", "content": content}
            if calls:
                clean["tool_calls"] = calls
            return ModelReply(clean, usage)
        except HTTPError as error:
            code, message = {
                401: ("model_auth_error", "模型密钥无效或没有访问权限"),
                403: ("model_auth_error", "模型访问被拒绝"),
                402: ("model_balance_error", "模型账户余额不足"),
                429: ("model_rate_limited", "模型请求受到限流，请稍后手动重试"),
            }.get(error.code, ("model_network_error", "模型服务请求失败"))
            raise ModelError(code, message) from None
        except (URLError, OSError, TimeoutError):
            raise ModelError("model_network_error", "模型连接失败或超时") from None
        except (ValueError, KeyError, IndexError, TypeError, ValidationError):
            raise ModelError("model_format_error", "模型响应格式不符合约定", usage=usage) from None


class ScriptedModel:
    """可注入的假模型；测试不访问网络，也不会使用评测答案。"""

    provider = "fake"
    name = "scripted-test"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def complete(self, messages, tools, **kwargs):
        self.calls.append({"messages": list(messages), "tools": tools, **kwargs})
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value


def tool_call(name, arguments, call_id="call-demo"):
    return ModelReply(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }
    )


def measured_call(model, messages, tools, **kwargs):
    started = time.monotonic()
    reply = model.complete(messages, tools, **kwargs)
    return reply, round((time.monotonic() - started) * 1000)
