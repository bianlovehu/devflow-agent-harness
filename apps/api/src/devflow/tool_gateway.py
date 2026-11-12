# 文件用途：只向模型开放当前任务绑定的只读证据，校验参数、范围、分页和重复调用。
import hashlib
import json
import re
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from devflow.errors import DomainError
from devflow.fixed_files import safe_path
from devflow.security import redact

MAX_RESULT_CHARS = 12000
ERROR_PATTERN = re.compile(
    r"error|exception|traceback|failed|failure|assert|not found|no matching|missing|exit code",
    re.IGNORECASE,
)


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    repo_id: str = Field(min_length=1, max_length=80)


class OverviewArgs(ToolArgs):
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=10, ge=1, le=20)


class ReadArgs(ToolArgs):
    evidence_id: str = Field(min_length=1, max_length=80)
    start_line: int = Field(default=1, ge=1, le=10000000)
    limit: int = Field(default=60, ge=1, le=100)


class FileArgs(ToolArgs):
    path: str = Field(min_length=1, max_length=480)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    start_line: int = Field(default=1, ge=1, le=10000000)
    limit: int = Field(default=60, ge=1, le=100)


class LogArgs(ReadArgs):
    mode: Literal["lines", "errors"] = "errors"


class SearchArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=500)


TOOLS = {
    "get_pr": (OverviewArgs, "获取固定版本 PR 元数据及证据目录，offset/limit 分页。"),
    "read_evidence": (ReadArgs, "按证据 ID 和原始行号读取 diff、资料或日志片段。"),
    "read_file": (FileArgs, "读取任务已采集的指定提交文件片段，必须使用完整 commit。"),
    "get_ci": (OverviewArgs, "获取固定 CI 状态和日志目录；PR 仅返回相同 head 的已采集 CI。"),
    "read_log": (LogArgs, "提取日志错误块及前后文，或按原始行号分页；保留全文制品指针。"),
    "get_linked_issues": (OverviewArgs, "读取采集时保存的同仓库关联 Issue。"),
    "search_knowledge": (
        SearchArgs,
        "检索本仓库有效版本的项目资料，返回最多6个片段及证据 ID、版本、原文行号。"
        "不能查询当前 GitHub 状态。",
    ),
}


def call_fingerprint(name, arguments):
    try:
        value = json.loads(arguments)
        if name in TOOLS:
            try:
                value = TOOLS[name][0].model_validate_json(arguments).model_dump()
            except ValidationError:
                pass
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (ValueError, TypeError):
        canonical = arguments
    return hashlib.sha256((name + "\n" + canonical).encode()).hexdigest()


def definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema.model_json_schema(),
            },
        }
        for name, (schema, description) in TOOLS.items()
    ]


def log_windows(content, context=3, maximum=4, *, start_line=1):
    lines = original_lines(content)
    windows = []
    for index, line in enumerate(lines):
        if not ERROR_PATTERN.search(line):
            continue
        start, end = max(1, index + 1 - context), min(len(lines), index + 1 + context)
        if end < start_line:
            continue
        start = max(start, start_line)
        if windows and start <= windows[-1][1] + 1:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        elif len(windows) < maximum:
            windows.append((start, end))
        else:
            break
    return windows


def original_lines(content):
    return content.replace("\r\n", "\n").replace("\r", "\n").removesuffix("\n").split("\n")


class ToolGateway:
    def __init__(
        self,
        repo_id,
        evidence,
        metadata,
        *,
        guard=lambda: None,
        emit=lambda *_: None,
        knowledge_search=None,
    ):
        self.repo_id = repo_id
        self.evidence = {item["id"]: item for item in evidence}
        self.metadata = metadata
        self.guard, self.emit = guard, emit
        self.observed = {}
        self.cache = {}
        self.knowledge_search = knowledge_search

    def _descriptor(self, item):
        return {
            key: item[key]
            for key in (
                "id",
                "source_type",
                "path",
                "version",
                "artifact_id",
                "start_line",
                "end_line",
            )
        }

    def catalog(self):
        return [self._descriptor(item) for item in self.evidence.values()]

    def _read(self, item, start, limit):
        lines = original_lines(item["content"])
        # 兼容旧文档把末尾换行算作额外一行的元数据；实际内容不能越界索引。
        available_end = min(item["end_line"], len(lines))
        if not item["start_line"] <= start <= available_end:
            raise DomainError(422, "invalid_line_range", "起始行超出证据范围")
        end = min(start + limit - 1, available_end)
        result_lines, size = [], 0
        for number in range(start, end + 1):
            line = lines[number - 1]
            if size + len(line) > 7000:
                if not result_lines:
                    raise DomainError(413, "tool_line_too_long", "单行超过工具限额，请核查全文制品")
                break
            result_lines.append({"line": number, "text": line})
            size += len(line)
        end = result_lines[-1]["line"]
        return {
            **self._descriptor(item),
            "start_line": start,
            "end_line": end,
            "lines": result_lines,
            "next_line": end + 1 if end < available_end else None,
            "full_artifact_id": item["artifact_id"],
            "stored_range": [item["start_line"], available_end],
            "source_truncated": item.get("capture_truncated"),
            "range_note": "next_line 仅表示保存材料的续读位置，不证明原始材料是否截断。",
        }

    def _dispatch(self, name, args):
        if name == "search_knowledge":
            if self.metadata.get("input_version", {}).get("use_knowledge") is False:
                return {"available": False, "code": "knowledge_disabled", "items": []}
            if self.knowledge_search is None:
                return {"available": False, "code": "knowledge_not_ready", "items": []}
            result = self.knowledge_search(args.query)
            for item in result.pop("_evidence", []):
                self.evidence[item["id"]] = item
            # 控制工具输出长度，未返回的片段不会被标记为已读。
            while (
                result.get("items")
                and len(json.dumps(result, ensure_ascii=False)) > MAX_RESULT_CHARS - 200
            ):
                result["items"].pop()
                result["truncated"] = True
            return result
        if name in {"get_pr", "get_ci", "get_linked_issues"}:
            kinds = {
                "get_pr": {"file", "diff", "document"},
                "get_ci": {"log", "document"},
                "get_linked_issues": {"issue"},
            }[name]
            items = [item for item in self.evidence.values() if item["source_type"] in kinds]
            page = items[args.offset : args.offset + args.limit]
            return {
                "metadata": self.metadata if args.offset == 0 else {},
                "items": [self._descriptor(item) for item in page],
                "next_offset": args.offset + args.limit
                if args.offset + args.limit < len(items)
                else None,
                "note": "目录不是证据正文；请读取片段后引用。仅覆盖已采集材料。",
            }
        if name == "read_file":
            safe_path(args.path)
            item = next(
                (
                    item
                    for item in self.evidence.values()
                    if (
                        item["source_type"] == "file"
                        and item["path"] == args.path
                        and item["version"] == args.commit
                    )
                ),
                None,
            )
        else:
            item = self.evidence.get(args.evidence_id)
        if item is None:
            raise DomainError(404, "tool_evidence_not_found", "当前任务未采集此版本的证据")
        if name == "read_log":
            if item["source_type"] != "log":
                raise DomainError(422, "invalid_log", "指定证据不是日志")
            if args.mode == "errors":
                # start_line 同样用于错误块续页，未返回的片段不能成为有效报告引用。
                windows = log_windows(item["content"], maximum=2, start_line=args.start_line)
                fragments = [
                    self._read(
                        item,
                        max(start, args.start_line),
                        min(end - max(start, args.start_line) + 1, args.limit),
                    )
                    for start, end in windows
                    if end >= args.start_line
                ][:2]
                # 错误块数量不代表完整日志已被检查。
                return {
                    "fragments": fragments,
                    "full_artifact_id": item["artifact_id"],
                    "note": "错误关键词提取，可能遗漏根因；可切换 lines 按行补查。",
                    "next_line": fragments[-1]["end_line"] + 1 if fragments else None,
                }
        return self._read(item, args.start_line, args.limit)

    def _mark_observed(self, result):
        if isinstance(result, dict):
            if "lines" in result and "id" in result:
                self.observed.setdefault(result["id"], []).append(
                    (result["start_line"], result["end_line"])
                )
            for value in result.values():
                self._mark_observed(value)
        elif isinstance(result, list):
            for value in result:
                self._mark_observed(value)

    def execute(self, name, arguments):
        self.guard()
        started = time.monotonic()
        self.emit("tool.started", {"tool": name, "read_only": True})
        duplicate = False
        try:
            if name not in TOOLS:
                raise DomainError(422, "unknown_tool", "工具不在只读白名单中")
            if len(arguments) > 8000:
                raise DomainError(413, "tool_arguments_too_large", "工具参数超过长度限制")
            args = TOOLS[name][0].model_validate_json(arguments)
            if args.repo_id != self.repo_id:
                raise DomainError(403, "tool_repository_denied", "工具只能访问当前任务登记的仓库")
            key = (name, args.model_dump_json())
            duplicate = key in self.cache
            result = (
                self.cache[key]
                if duplicate and name != "search_knowledge"
                else self._dispatch(name, args)
            )
            serialized = json.dumps(result, ensure_ascii=False)
            if len(serialized) > MAX_RESULT_CHARS:
                raise DomainError(
                    413, "tool_result_too_large", "结果超过限制，请缩小 limit 分页读取"
                )
            self.guard()
            if time.monotonic() - started > (60 if name == "search_knowledge" else 5):
                raise DomainError(504, "tool_timeout", "本地证据读取超时")
            self.cache[key] = result
            self._mark_observed(result)
            response = {"ok": True, "duplicate": duplicate, "data": result}
        except ValidationError:
            response = {
                "ok": False,
                "error": {"code": "invalid_tool_arguments", "message": "工具参数不符合 schema"},
            }
        except DomainError as error:
            response = {"ok": False, "error": {"code": error.code, "message": error.message}}
        self.emit(
            "tool.completed",
            {
                "tool": name,
                "ok": response["ok"],
                "duplicate": duplicate,
                "duration_ms": round((time.monotonic() - started) * 1000),
                **({"error": response["error"]} if not response["ok"] else {}),
            },
        )
        return redact(response)
