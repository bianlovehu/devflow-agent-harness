# 文件用途：显式验证所选供应商的真实工具调用与 JSON 输出，仅打印状态和用量。
import json

from devflow.config import get_settings
from devflow.model_gateway import DeepSeekModel, ModelError
from pydantic import BaseModel, ConfigDict


class ProbeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


def main():
    settings = get_settings()
    if settings.model_provider == "fake":
        raise SystemExit("Set MODEL_PROVIDER=aliyun or deepseek for this explicit probe")
    model = DeepSeekModel(settings)
    messages = [
        {
            "role": "system",
            "content": "先调用 read_probe 工具一次获取 value，再输出 json 对象，"
            '格式 {"value": 整数}。',
        },
        {"role": "user", "content": "请读取工具里的值，不要猜测。"},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_probe",
                "description": "读取验证值。",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }
    ]
    try:
        first = model.complete(messages, tools, max_tokens=256)
        calls = first.message.get("tool_calls", [])
        if len(calls) != 1 or calls[0]["function"]["name"] != "read_probe":
            raise ValueError("Expected one tool call")
        messages += [
            first.message,
            {"role": "tool", "tool_call_id": calls[0]["id"], "content": '{"value": 731}'},
        ]
        second = model.complete(messages, [], max_tokens=256)
        answer = ProbeAnswer.model_validate_json(second.message["content"])
        assert answer.value == 731
        print(
            json.dumps(
                {
                    "status": "ok",
                    "provider": model.provider,
                    "model": model.name,
                    "tool_calls": 1,
                    "json_verified": True,
                    "total_tokens": first.usage.total_tokens + second.usage.total_tokens,
                },
                ensure_ascii=False,
            )
        )
    except ModelError as error:
        print(
            json.dumps(
                {"status": "error", "code": error.code, "message": error.message},
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
