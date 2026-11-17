# 文件用途：代码证据 MCP 的固定白名单、严格输入/输出 schema 和版本指纹。
import hashlib
import json

from jsonschema import Draft202012Validator
from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict

from devflow.analysis.tool_gateway import CodeSearchArgs, CodeTreeArgs, FileArgs
from devflow.code.schemas import CodeFileResponse, CodeSearchResponse, CodeTreeResponse
from devflow.core.errors import DomainError

SERVER_NAME = "devflow-code-evidence"
SERVER_VERSION = "1.0.0"
CONTRACT_VERSION = "code-evidence-v1"
BACKEND = "mcp-stdio-v1"
MAPPING = {"list_code_tree": "repo_tree", "search_code": "repo_search", "read_file": "repo_read"}
INPUTS = {"repo_tree": CodeTreeArgs, "repo_search": CodeSearchArgs, "repo_read": FileArgs}
OUTPUTS = {
    "repo_tree": CodeTreeResponse,
    "repo_search": CodeSearchResponse,
    "repo_read": CodeFileResponse,
}
DESCRIPTIONS = {
    "repo_tree": "列出任务固定提交的目录，不返回正文。",
    "repo_search": "在任务固定提交中做字面量搜索，返回正文片段或路径。",
    "repo_read": "读取任务固定提交的文件行段。",
}


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    code: str
    message: str
    status: int


def strict_objects(value):
    if isinstance(value, dict):
        value = {key: strict_objects(child) for key, child in value.items()}
        if value.get("type") == "object" and "properties" in value:
            value["additionalProperties"] = False
    elif isinstance(value, list):
        value = [strict_objects(child) for child in value]
    return value


def output_schema(name):
    data = strict_objects(OUTPUTS[name].model_json_schema())
    definitions = data.pop("$defs", {})
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ok": {"type": "boolean"},
            "data": {"anyOf": [data, {"type": "null"}]},
            "error": {"anyOf": [ToolError.model_json_schema(), {"type": "null"}]},
        },
        "required": ["ok", "data", "error"],
        "$defs": definitions,
    }


def tools(pid=None):
    return [
        Tool(
            name=name,
            description=DESCRIPTIONS[name],
            input_schema=INPUTS[name].model_json_schema(),
            output_schema=output_schema(name),
            annotations=ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
            meta={"contract_version": CONTRACT_VERSION, **({"pid": pid} if pid else {})},
        )
        for name in INPUTS
    ]


def fingerprint(values):
    schemas = sorted(
        [{"name": t.name, "input": t.input_schema, "output": t.output_schema} for t in values],
        key=lambda item: item["name"],
    )
    return hashlib.sha256(
        json.dumps(schemas, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_result(name, value, is_error):
    try:
        Draft202012Validator(output_schema(name)).validate(value)
        if (
            value["ok"] == is_error
            or (value["ok"] and (value["data"] is None or value["error"] is not None))
            or (not value["ok"] and (value["data"] is not None or value["error"] is None))
        ):
            raise ValueError("inconsistent result")
        if not value["ok"]:
            error = ToolError.model_validate(value["error"])
            raise DomainError(error.status, error.code, error.message)
        return (
            OUTPUTS[name]
            .model_validate_json(json.dumps(value["data"]), strict=True)
            .model_dump(mode="json")
        )
    except DomainError:
        raise
    except Exception as error:
        raise DomainError(502, "mcp_result_invalid", "代码证据服务返回不符合契约的结果") from error
