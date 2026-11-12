# 文件用途：仅接收评测输入，运行实际 Agent/工具循环；不向模型传递参考标注。
import hashlib
import time
from uuid import NAMESPACE_URL, uuid5

from devflow.agent import AnalysisRunner, model_configuration
from devflow.errors import DomainError
from devflow.fake_model import FixtureModel
from devflow.knowledge import lexical_terms
from devflow.model_gateway import DeepSeekModel
from devflow.runtime_policy import cost
from devflow.security import redact
from devflow.tool_gateway import ToolGateway, original_lines

RETRIEVAL_PROFILE = {"adapter": "snapshot-keyword-v1", "limit": 6, "min_overlap": 1}


def evaluation_configuration(settings):
    configuration = model_configuration(settings)
    configuration["budget"] = {
        "max_model_calls": 6,
        "max_tool_calls": 12,
        "max_total_tokens": 600000,
        "timeout_seconds": 600,
    }
    if settings.model_provider == "fake":
        configuration.update(model="fixture-demo-v1", base_url="offline")
    return configuration


def build_gateway(case):
    # 固定快照适配器用于 Agent 评测，不接触业务数据库或读取标注。
    versions = {
        rev: hashlib.sha1(
            "\n".join(s.content for s in case.sources if s.revision == rev).encode() + rev.encode()
        ).hexdigest()
        for rev in ["base", "head"]
    }
    evidence = [
        {
            "id": str(uuid5(NAMESPACE_URL, f"devflow-eval/{case.case_id}/{s.key}")),
            "artifact_id": str(
                uuid5(NAMESPACE_URL, f"devflow-eval/artifact/{case.case_id}/{s.key}")
            ),
            "source_key": s.key,
            "source_type": s.source_type,
            "path": s.path,
            "version": versions[s.revision],
            "start_line": 1,
            "end_line": len(original_lines(s.content)),
            "content": s.content,
            "content_sha256": hashlib.sha256(s.content.encode()).hexdigest(),
        }
        for s in case.sources
    ]
    documents = [e for e in evidence if e["source_type"] == "document"]

    def search(query):
        query_terms = set(lexical_terms(query))
        ranked = sorted(
            documents,
            key=lambda e: (-len(query_terms & set(lexical_terms(e["content"]))), e["source_key"]),
        )
        hits = [e for e in ranked if query_terms & set(lexical_terms(e["content"]))][:6]
        return {
            "available": True,
            "items": [
                {
                    key: e[key]
                    for key in ["id", "artifact_id", "path", "version", "start_line", "end_line"]
                }
                | {
                    "version_id": e["version"],
                    "lines": [
                        {"line": i, "text": line}
                        for i, line in enumerate(original_lines(e["content"]), 1)
                    ],
                }
                for e in hits
            ],
            "_evidence": hits,
        }

    gateway = ToolGateway(
        "eval-repo",
        [e for e in evidence if e["source_type"] != "document"],
        {
            "data_source": "evaluation_fixture",
            "version_kind": "derived_snapshot_id; not a remote Git commit",
            "input_version": {
                "use_knowledge": case.task_type == "knowledge_qa",
                "resources": []
                if case.task_type == "knowledge_qa"
                else [
                    {
                        "kind": "pull_request" if case.task_type == "pr_review" else "ci_run",
                        **({"base_sha": versions["base"]} if case.task_type == "pr_review" else {}),
                        "head_sha": versions["head"],
                    }
                ],
            },
        },
        knowledge_search=search,
    )
    return gateway, evidence


def execute_case(
    case,
    settings,
    *,
    knowledge_search=None,
    configuration_updates=None,
    history=None,
    charge_source=None,
):
    gateway, evidence = build_gateway(case)
    if knowledge_search is not None:
        gateway.knowledge_search = knowledge_search if case.task_type == "knowledge_qa" else None
        evidence = [e for e in evidence if e["source_type"] != "document"]
    configuration = evaluation_configuration(settings)
    configuration.update(configuration_updates or {})
    model = (
        FixtureModel()
        if settings.model_provider == "fake"
        else DeepSeekModel(
            settings, purpose="evaluation", source=charge_source or "eval:" + case.case_id
        )
    )
    runner = AnalysisRunner(
        model, gateway, case.task_type, case.question, configuration, history=history
    )
    started = time.monotonic()
    try:
        result, error = runner.run(), None
    except DomainError as exc:
        result, error = {}, {"code": exc.code, "message": exc.message}
    except Exception as exc:
        # 内部异常保留类型，不输出可能含端点密钥的异常原文。
        result, error = {}, {"code": "evaluation_internal_error", "type": type(exc).__name__}
    evidence = list({e["id"]: e for e in [*evidence, *gateway.evidence.values()]}.values())
    usage = {
        "prompt_tokens": runner.prompt_tokens,
        "completion_tokens": runner.completion_tokens,
        "total_tokens": runner.total_tokens,
    }
    unknown = any("response" not in call and "usage" not in call for call in runner.trace["calls"])
    quote = configuration.get("pricing_snapshot")
    estimate = (
        "0"
        if settings.model_provider == "fake"
        else str(cost(runner.prompt_tokens, runner.completion_tokens, quote))
        if quote
        else None
    )
    return redact(
        {
            "result": result,
            "error": error,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "evidence": evidence,
            "observed": gateway.observed,
            "trace": runner.trace,
            "usage": usage,
            "usage_unknown": unknown,
            "known_usage_cost_cny": estimate,
        }
    )
