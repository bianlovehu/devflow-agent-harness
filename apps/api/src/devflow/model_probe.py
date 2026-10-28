# 文件用途：显式执行一次最小 DeepSeek 连通测试，不参与日常轮询。
"""Explicit, one-request connectivity probe; never used by health polling."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from devflow.config import Settings, get_settings


def probe_deepseek(settings: Settings) -> dict[str, object]:
    # 仅显式调用时发送一次小请求，输出用量但不输出密钥或响应头。
    key = settings.deepseek_api_key.get_secret_value().strip()
    if not key:
        return {"status": "not_configured", "message": "请先设置服务端 DEEPSEEK_API_KEY"}
    payload = {
        "model": settings.deepseek_model,
        "messages": [{"role": "user", "content": "Reply with exactly OK."}],
        "thinking": {"type": "disabled"},
        "max_tokens": 8,
        "stream": False,
    }
    request = Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        # 只向代码中固定的官方端点发送请求，错误响应不输出鉴权信息。
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        content = result["choices"][0]["message"]["content"].strip()
        usage = result.get("usage", {})
        return {
            "status": "ok" if content == "OK" else "unexpected_response",
            "model": result.get("model", settings.deepseek_model),
            "verified": content == "OK",
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    except HTTPError as exc:
        messages = {
            401: "密钥无效或无访问权限",
            402: "账户余额不足",
            429: "请求受到限流",
        }
        return {
            "status": "error",
            "http_status": exc.code,
            "message": messages.get(exc.code, "DeepSeek 请求失败"),
        }
    except (URLError, TimeoutError, OSError):
        return {"status": "error", "message": "无法连接 DeepSeek，请检查网络或稍后重试"}
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return {"status": "error", "message": "DeepSeek 响应格式不符合预期"}


def main() -> None:
    result = probe_deepseek(get_settings())
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
