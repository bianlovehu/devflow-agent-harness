# 文件用途：统一脱敏待分析资料、模型消息和对外输出，保持原始行号。
import re

from fastapi.responses import JSONResponse

PATTERNS = [
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"(?i)(\b(?:authorization\s*[:=]\s*)?bearer\s+)[A-Za-z0-9._~+/-]{12,}=*"),
    re.compile(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)"
        r"\s*[:=]\s*[\"']?)[A-Za-z0-9_./+~-]{8,}"
    ),
]


def redact_text(value):
    for pattern in PATTERNS:
        value = pattern.sub(
            lambda match: (match[1] if match.lastindex else "") + "[REDACTED]", value
        )
    return value


def redact(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: redact(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(child) for child in value]
    return value


class RedactedJSONResponse(JSONResponse):
    def render(self, content):
        return super().render(redact(content))
