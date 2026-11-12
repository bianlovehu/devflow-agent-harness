# 文件用途：统一服务端运行上限与带来源的保守模型报价。
from decimal import ROUND_UP, Decimal
from urllib.parse import urlsplit

from devflow.errors import DomainError

POLICY_VERSION = "runtime-budget-v1"
MAX_INPUT_TOKENS = 120000
MAX_OUTPUT_TOKENS = 20000
MAX_TOTAL_TOKENS = 600000
MAX_MODEL_CALLS = 6
MAX_TOOL_CALLS = 12
MAX_TIMEOUT_SECONDS = 600
MAX_MODEL_SECONDS = 90
REPEAT_LIMIT = 3
MONEY_QUANTUM = Decimal("0.00000001")


def limits():
    return {
        "input_tokens": MAX_INPUT_TOKENS,
        "output_tokens": MAX_OUTPUT_TOKENS,
        "total_tokens": MAX_TOTAL_TOKENS,
        "model_calls": MAX_MODEL_CALLS,
        "tool_calls": MAX_TOOL_CALLS,
        "timeout_seconds": MAX_TIMEOUT_SECONDS,
        "model_timeout_seconds": MAX_MODEL_SECONDS,
        "repeat_limit": REPEAT_LIMIT,
    }


def pricing(provider, model, base_url):
    host = urlsplit(base_url).hostname or ""
    beijing = host == "dashscope.aliyuncs.com" or host.endswith(".cn-beijing.maas.aliyuncs.com")
    if provider != "aliyun" or model != "deepseek-v4.1-flash" or not beijing:
        raise DomainError(
            422, "pricing_not_configured", "当前模型或地域没有已核查报价，真实请求未发送"
        )
    return {
        "version": "aliyun-beijing-deepseek-v4.1-flash-2026-11-04",
        "provider": provider,
        "model": model,
        "region": "cn-beijing",
        "currency": "CNY",
        "input_per_million": "2",
        "output_per_million": "8",
        "source": "https://help.aliyun.com/zh/model-studio/deepseek-v4-1-flash",
        "verified_on": "2026-11-04",
        "basis": "忙时目录价；不抵扣缓存、优惠或免费额度",
    }


def cost(input_tokens, output_tokens, quote):
    return (
        (
            Decimal(input_tokens) * Decimal(quote["input_per_million"])
            + Decimal(output_tokens) * Decimal(quote["output_per_million"])
        )
        / Decimal(1000000)
    ).quantize(MONEY_QUANTUM, rounding=ROUND_UP)
