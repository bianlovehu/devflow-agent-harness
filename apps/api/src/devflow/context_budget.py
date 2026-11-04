# 文件用途：分层压缩模型输入，保存证据指针、工具配对及可量化的预算记录。
import copy
import json
import math
import re

from devflow.errors import DomainError


def estimate_tokens(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    # 未声称等同供应商 tokenizer：ASCII 每 3 字符、非 ASCII 每 UTF-8 字节估算。
    return math.ceil(sum(1 / 3 if ord(c) < 128 else len(c.encode("utf-8")) for c in text))


def pointers(value):
    if isinstance(value, dict):
        result = {
            k: v
            for k, v in value.items()
            if k
            in {
                "id",
                "evidence_id",
                "artifact_id",
                "full_artifact_id",
                "version",
                "version_id",
                "path",
                "start_line",
                "end_line",
                "next_line",
                "next_offset",
                "error",
                "unconfirmed",
                "warnings",
                "coverage_complete",
                "truncated",
            }
        }
        children = [pointers(v) for v in value.values() if isinstance(v, (dict, list))]
        if any(children):
            result["sources"] = [v for v in children if v]
        return result
    if isinstance(value, list):
        return [found for item in value if (found := pointers(item))]
    return None


def compress_context(messages, tools, maximum=12000):
    result = copy.deepcopy(messages)
    before = estimate_tokens(result) + estimate_tokens(tools)
    stages = []

    def size():
        return estimate_tokens(result) + estimate_tokens(tools)

    # 1. 去重只替换正文，不删除 assistant/tool 消息，保留协议中的配对关系。
    seen = set()
    for message in result:
        if message.get("role") != "tool":
            continue
        content = message.get("content", "")
        if content in seen:
            try:
                source = pointers(json.loads(content))
            except ValueError:
                source = None
            replacement = json.dumps({"duplicate": True, "sources": source}, ensure_ascii=False)
            if estimate_tokens(replacement) < estimate_tokens(content):
                message["content"] = replacement
        seen.add(content)
    if size() < before:
        stages.append("deduplicate")
    # 2. 检索结果按原始相关性排序，从低排名向前裁剪，保留来源指针。
    if size() > maximum:
        for message in result:
            if message.get("role") != "tool":
                continue
            try:
                value = json.loads(message["content"])
            except ValueError:
                continue
            data = value.get("data", {})
            hits = data.get("items", []) if isinstance(data, dict) else []
            for hit in reversed(hits):
                if size() <= maximum:
                    break
                if "lines" in hit and "version_id" in hit:
                    hit["source_pointer"] = pointers(hit)
                    hit.pop("lines")
                    hit["compressed"] = True
                    message["content"] = json.dumps(value, ensure_ascii=False)
                    stages.append("prune_evidence")
    # 3. 旧工具结果压缩为来源与未解决事项；最近一批结果优先保留。
    for message in result:
        if size() <= maximum:
            break
        if message.get("role") == "tool":
            try:
                value = json.loads(message["content"])
            except ValueError:
                value = {}
            message["content"] = json.dumps(
                {
                    "compressed": True,
                    "sources": pointers(value),
                    "note": "正文已压缩；可按来源 ID 和原始行号重新读取，原始输入在上下文制品中。",
                },
                ensure_ascii=False,
            )
            stages.append("compress_tools")
    # 4. 历史单独封装，当前请求及系统指令不参与摘要。
    if size() > maximum:
        for message in result:
            if message.get("role") != "user":
                continue
            try:
                value = json.loads(message["content"])
            except (ValueError, TypeError):
                continue
            if "conversation_history" not in value:
                continue
            summaries = []
            history = value["conversation_history"]
            recent = []
            while history and len(recent) < 2 and estimate_tokens(history[-1]) < maximum // 4:
                recent.insert(0, history.pop())
            for item in history:
                text = item["content"]
                # 保留约束/待确认句；超多约束不能安全压缩时会明确停止，避免静默丢失。
                important = [
                    line
                    for line in re.split(r"[\n。]", text)
                    if re.search(
                        r"必须|禁止|不能|不得|不要|尚未|待确认|未解决|约束|must|never|unresolved|TODO",
                        line,
                        re.I,
                    )
                ]
                summaries.append(
                    {
                        "id": item["id"],
                        "role": item["role"],
                        "summary": text[:180],
                        "constraints_and_open_questions": important,
                        "sources": pointers(item),
                        "source_ids": re.findall(
                            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", text
                        ),
                    }
                )
            message["content"] = json.dumps(
                {"conversation_summary": summaries, "recent_messages": recent}, ensure_ascii=False
            )
            stages.append("summarize_history")
    after = size()
    if after > maximum:
        raise DomainError(
            422, "budget_exceeded", "系统指令、当前请求和必要约束超过上下文预算，请缩小请求"
        )
    return result, {
        "estimated_before": before,
        "estimated_input": after,
        "saved_tokens": before - after,
        "input_limit": maximum,
        "stages": list(dict.fromkeys(stages)),
    }
