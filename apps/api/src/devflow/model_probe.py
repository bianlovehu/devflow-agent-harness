# 文件用途：通过统一预算网关显式执行一次最小连通探针，不参与健康轮询。
import json

from devflow.config import Settings, get_settings
from devflow.errors import DomainError
from devflow.model_gateway import DeepSeekModel


def probe_deepseek(settings: Settings, *, ledger=None, opener=None) -> dict:
    if not settings.deepseek_api_key.get_secret_value().strip():
        return {"status": "not_configured", "message": "请先设置服务端 DEEPSEEK_API_KEY"}
    settings = settings.model_copy(update={"model_provider": "deepseek"})
    model = DeepSeekModel(
        settings, ledger=ledger, opener=opener, purpose="probe", source="connectivity_probe"
    )
    try:
        reply = model.complete(
            [{"role": "user", "content": 'Reply with json: {"ok":true}.'}], [], max_tokens=16
        )
        ok = json.loads(reply.message["content"]) == {"ok": True}
        return {
            "status": "ok" if ok else "unexpected_response",
            "model": model.name,
            "verified": ok,
            **reply.usage.model_dump(),
        }
    except DomainError as error:
        return {"status": "error", "code": error.code, "message": error.message}


def main():
    settings = get_settings()
    if settings.model_provider == "fake":
        result = {"status": "ok", "provider": "fake", "message": "离线假模型，不发送请求"}
    elif settings.model_provider == "deepseek":
        result = probe_deepseek(settings)
    else:
        model = DeepSeekModel(settings, purpose="probe", source="connectivity_probe")
        try:
            reply = model.complete(
                [{"role": "system", "content": 'Reply with json: {"ok":true}.'}], [], max_tokens=16
            )
            result = {
                "status": "ok"
                if json.loads(reply.message["content"]) == {"ok": True}
                else "unexpected_response",
                "model": model.name,
                "provider": model.provider,
                **reply.usage.model_dump(),
            }
        except DomainError as error:
            result = {"status": "error", "code": error.code, "message": error.message}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
