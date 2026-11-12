# 文件用途：基于可见工具片段提供明确标记的离线演示假模型，不读取评测答案。
import json
from difflib import SequenceMatcher

from devflow.model_gateway import ModelReply


class FixtureModel:
    provider = "fake"
    name = "fixture-demo-v1"

    @staticmethod
    def report_reply(report, request, fragments):
        # 只给原有演示结果补齐新格式；不增加识别规则，也不声称已做语义复核。
        if request.get("report_version") == "2":
            report.update(report_version="2", boundary_claims=[])
            for finding in report["findings"]:
                direct = []
                for citation in finding["evidence"]:
                    for fragment in fragments:
                        if fragment.get("id") != citation["evidence_id"]:
                            continue
                        quote = "\n".join(
                            v["text"]
                            for v in fragment["lines"]
                            if citation["start_line"] <= v["line"] <= citation["end_line"]
                        )
                        if quote:
                            direct.append(
                                {
                                    "citation": citation,
                                    "quote": quote[:2000],
                                    "observation": "离线规则命中了这段材料，结论尚待复核。",
                                }
                            )
                            break
                finding.update(
                    nature="hypothesis",
                    basis="current",
                    claim_type="run_result"
                    if report["task_type"] == "ci_debug"
                    else "code_behavior",
                    root_cause=finding["title"],
                    direct_evidence=direct,
                    prerequisites=["以当前固定版本和已读材料为限。"],
                    unconfirmed_conditions=["演示规则的判断是否成立，需要另行复核。"],
                    severity_reason="原有离线演示规则的等级，不代表实际影响已经确认。",
                    consequences=[finding["explanation"]],
                    reachability="unknown",
                    call_chain=[],
                )
        return ModelReply({"role": "assistant", "content": json.dumps(report, ensure_ascii=False)})

    @staticmethod
    def changed_lines(request, fragments):
        """按工具已读的 base/head 比较，只把 head 新增/替换行作为演示风险候选。"""
        resources = request.get("metadata", {}).get("input_version", {}).get("resources", [])
        resource = next((r for r in resources if r.get("kind") == "pull_request"), None)
        if resource is None:
            return None
        base, head = {}, {}
        ends = {
            (item["path"], item["version"]): item["end_line"]
            for item in request["catalog"]
            if item["source_type"] == "file"
        }
        for fragment in fragments:
            if fragment.get("source_type") != "file":
                continue
            target = (
                base
                if fragment.get("version") == resource.get("base_sha")
                else head
                if fragment.get("version") == resource.get("head_sha")
                else None
            )
            if target is not None:
                target.setdefault(fragment.get("path"), {}).update(
                    {line["line"]: line["text"] for line in fragment["lines"]}
                )
        changed = {}
        for path, lines in head.items():
            # 仅比较两边从第 1 行开始、连续且已读完的正文；片段不足时不猜测新增缺陷。
            before = base.get(path, {})
            if (
                not before
                or sorted(before) != list(range(1, max(before) + 1))
                or sorted(lines) != list(range(1, max(lines) + 1))
                or max(before) != ends.get((path, resource.get("base_sha")))
                or max(lines) != ends.get((path, resource.get("head_sha")))
            ):
                continue
            matcher = SequenceMatcher(
                a=[before[n] for n in sorted(before)],
                b=[lines[n] for n in sorted(lines)],
                autojunk=False,
            )
            changed[path] = {
                number + 1
                for tag, _, _, start, end in matcher.get_opcodes()
                if tag in {"replace", "insert"}
                for number in range(start, end)
            }
        return resource.get("head_sha"), changed

    def complete(self, messages, tools, **kwargs):
        request = json.loads(messages[1]["content"])
        tool_messages = [message for message in messages if message["role"] == "tool"]
        if not tool_messages:
            calls = []
            if request["task_type"] == "knowledge_qa" or request.get("metadata", {}).get(
                "input_version", {}
            ).get("use_knowledge"):
                calls.append(
                    {
                        "id": "fixture-knowledge",
                        "type": "function",
                        "function": {
                            "name": "search_knowledge",
                            "arguments": json.dumps(
                                {"repo_id": request["repo_id"], "query": request["question"][:500]}
                            ),
                        },
                    }
                )
            for item in request["catalog"]:
                if item["source_type"] not in {"file", "diff", "log"}:
                    continue
                name = "read_log" if item["source_type"] == "log" else "read_evidence"
                args = {"repo_id": request["repo_id"], "evidence_id": item["id"], "limit": 60}
                calls.append(
                    {
                        "id": f"fixture-{len(calls)}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                )
            return ModelReply({"role": "assistant", "content": None, "tool_calls": calls[:10]})
        fragments = []

        def collect(value):
            if isinstance(value, dict):
                if "lines" in value:
                    fragments.append(value)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        for message in tool_messages:
            collect(json.loads(message["content"]))
        documents = [f for f in fragments if "version_id" in f]
        citations = [
            {"evidence_id": f["id"], "start_line": f["start_line"], "end_line": f["end_line"]}
            for f in documents[:2]
        ]
        if request["task_type"] == "knowledge_qa":
            excerpts = [" ".join(line["text"] for line in f["lines"])[:1800] for f in documents[:2]]
            report = {
                "task_type": "knowledge_qa",
                "summary": "离线假模型演示：展示检索到的资料摘录。",
                "answer": "资料摘录：" + "\n".join(excerpts)
                if excerpts
                else "证据不足：当前仓库没有命中的有效资料，请上传相关文档后重新提问。",
                "answer_evidence": citations,
                "findings": [],
                "verification_steps": ["点击引用核查原文和版本。"],
                "suggestions": [],
                "unconfirmed": ["规则驱动的假模型，只摘录检索结果，不代表真实模型的综合回答。"],
                "scope": [f"检索当前仓库的有效资料版本，返回 {len(documents)} 个片段。"],
            }
            return self.report_reply(report, request, fragments)
        findings = []
        ci = request["task_type"] == "ci_debug"
        stage = "未知"
        patterns = (
            (
                (
                    "return list(tasks)",
                    "任务列表移除了所有者筛选",
                    "high",
                    "列表直接返回全部输入任务，可能让用户看到其他所有者的任务。",
                    "恢复 owner_id 与 actor_id 筛选，补充跨用户访问测试。",
                ),
                (
                    'labels = payload.get("labels", [])',
                    "显式 null 标签不再被接受",
                    "medium",
                    "get 的默认值只处理键缺失，显式 None 会进入列表类型校验并抛出 ValueError。",
                    "恢复 None 分支，分别验证缺省、null、空列表和非法类型。",
                ),
            )
            if not ci
            else (
                (
                    "No matching distribution",
                    "依赖版本无法从当前索引解析（根因假设）",
                    "high",
                    "安装日志显示找不到指定分发版本，测试阶段未启动；还需核查版本、索引和平台兼容性。",
                    "核实依赖发布版本与索引配置，再重新安装验证。",
                ),
                (
                    "DATABASE_URL is required",
                    "配置校验缺少 DATABASE_URL（根因假设）",
                    "high",
                    "运行在配置校验阶段退出，日志明确报告必需配置缺失。",
                    "在 CI secret/env 中设置正确连接配置，不要将凭据写入日志。",
                ),
                (
                    "FAILED tests/test_service.py::test_null_labels_are_empty",
                    "null 标签测试失败（根因假设）",
                    "medium",
                    "测试期望显式 null 转换为空列表，但日志显示 ValueError。"
                    "代码根因需读取对应提交后确认。",
                    "检查 None 分支，并在修复后运行相关回归测试。",
                ),
            )
        )
        change_scope = None if ci else self.changed_lines(request, fragments)
        for needle, title, severity, explanation, suggestion in patterns:
            for fragment in fragments:
                # 历史资料中的报错示例不能被当作本次代码或 CI 已发生的问题。
                if "version_id" in fragment:
                    continue
                if change_scope is not None:
                    version, changed = change_scope
                    if fragment.get("source_type") != "file" or fragment.get("version") != version:
                        continue
                match = next(
                    (
                        line
                        for line in fragment["lines"]
                        if needle in line["text"]
                        and not line["text"].startswith("-")
                        and (
                            change_scope is None
                            or line["line"] in changed.get(fragment.get("path"), set())
                        )
                    ),
                    None,
                )
                if match:
                    findings.append(
                        {
                            "title": title,
                            "severity": severity,
                            "explanation": explanation,
                            "suggestion": suggestion,
                            "evidence": [
                                {
                                    "evidence_id": fragment["id"],
                                    "start_line": match["line"],
                                    "end_line": match["line"],
                                }
                            ],
                        }
                    )
                    break
        if ci and findings:
            text = findings[0]["title"]
            stage = "安装依赖" if "依赖" in text else "配置校验" if "配置" in text else "测试"
        if documents:
            for finding in findings:
                finding["evidence"] += citations[:1]
                finding["explanation"] += (
                    " 项目资料补充约束："
                    + " ".join(line["text"] for line in documents[0]["lines"])[:350]
                )
        report = {
            "task_type": request["task_type"],
            "summary": f"离线假模型演示：根据已读片段识别 {len(findings)} 项待核验问题。",
            "findings": findings,
            "failure_stage": stage if ci else None,
            "verification_steps": [
                "人工核查所列固定版本证据。",
                "按建议在受控环境运行回归测试；本系统未执行代码。",
            ],
            "suggestions": [item["suggestion"] for item in findings],
            "unconfirmed": [
                "这是规则驱动的假模型演示，不代表真实模型分析。",
                "未检查未采集文件，也未执行测试。",
            ],
            "scope": [
                f"只检查当前任务工具返回的 {len(fragments)} 个片段；"
                f"其中项目资料 {len(documents)} 个。"
            ],
        }
        return self.report_reply(report, request, fragments)
