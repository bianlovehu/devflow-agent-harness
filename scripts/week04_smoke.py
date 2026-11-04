# 文件用途：用真实本地向量模型导入样例资料，验证中英召回和 PR/CI/知识问答演示链路。
import argparse
import json
from pathlib import Path
from uuid import uuid4

from devflow.artifact_store import ArtifactStore
from devflow.config import PROJECT_ROOT, get_settings
from devflow.data_source import fixture_source
from devflow.database import create_database_engine
from devflow.knowledge import search_knowledge, upload_document
from devflow.models import KnowledgeVersion, RunRecord
from devflow.reports import report_markdown, require_report
from devflow.worker import Worker
from devflow.workflow_contracts import ConversationCreate, RunCreate
from devflow.workflows import create_conversation, create_run
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="显式调用 .env 中的真实模型供应商")
    parser.add_argument("--output", default="data/week04-proof.json")
    parser.add_argument("--import-only", action="store_true", help="仅导入文档，不创建分析任务")
    parser.add_argument(
        "--task", choices=["all", "knowledge_qa", "pr_review", "ci_debug"], default="all"
    )
    args = parser.parse_args()
    settings = get_settings().model_copy(
        update={
            "data_source": "fixture",
            "fixture_storage": "database",
            "analysis_executor": "agent",
            "simulation_step_seconds": 0,
        }
    )
    if not args.real:
        settings = settings.model_copy(update={"model_provider": "fake"})
    elif settings.model_provider == "fake":
        raise SystemExit("--real 需要先在 .env 中配置真实模型")
    engine, store = create_database_engine(settings), ArtifactStore()
    proof = {"provider": settings.model_provider, "documents": [], "retrieval": [], "runs": []}
    try:
        for document in fixture_source().dataset.documents:
            with Session(engine, expire_on_commit=False) as session:
                doc_id, version_id, duplicate = upload_document(
                    session,
                    settings,
                    store,
                    document.repo_id,
                    document.id + ".md",
                    document.content.encode(),
                    source="fixture",
                )
                version = session.get(KnowledgeVersion, version_id)
                assert version.status == "ready", version.error_message
                proof["documents"].append(
                    {
                        "document_id": str(doc_id),
                        "version_id": str(version_id),
                        "duplicate": duplicate,
                        "chunks": version.chunk_count,
                    }
                )
        with Session(engine, expire_on_commit=False) as session:
            english = PROJECT_ROOT / "fixtures" / "knowledge" / "owner-policy.en.md"
            doc_id, version_id, duplicate = upload_document(
                session,
                settings,
                store,
                "repo-taskboard",
                english.name,
                english.read_bytes(),
                source="fixture",
            )
            version = session.get(KnowledgeVersion, version_id)
            assert version.status == "ready", version.error_message
            proof["documents"].append(
                {
                    "document_id": str(doc_id),
                    "version_id": str(version_id),
                    "duplicate": duplicate,
                    "chunks": version.chunk_count,
                }
            )
        if args.import_only:
            print(json.dumps(proof["documents"], indent=2))
            return
        queries = [
            "用户能否看到其他人的任务？",
            "显式 null 标签应该如何处理？",
            "依赖安装找不到分发版本时如何排查？",
        ]
        for query in queries:
            with Session(engine) as session:
                found = search_knowledge(session, "repo-taskboard", query)
                assert found["items"], query
                proof["retrieval"].append({"query": query, **found})
        assert any(
            hit["filename"] == "owner-policy.en.md" for hit in proof["retrieval"][0]["items"]
        ), "中文问题应能召回英文策略"
        worker = Worker(engine, settings, store)
        for task, target, use_knowledge, question in [
            (
                "knowledge_qa",
                None,
                True,
                "项目对任务所有者隔离和 labels=null 有什么约束？请引用资料。",
            ),
            ("pr_review", "102", False, "检查这个 PR 的所有者隔离风险，并说明依据与设计约束。"),
            ("pr_review", "102", True, "检查这个 PR 的所有者隔离风险，并说明依据与设计约束。"),
            ("ci_debug", "202", True, "结合历史复盘排查 labels null 测试失败，给出验证建议。"),
        ]:
            if args.task != "all" and args.task != task:
                continue
            with Session(engine, expire_on_commit=False) as session:
                conversation = create_conversation(
                    session,
                    ConversationCreate(repo_id="repo-taskboard", title="第四周演示 · " + task),
                    settings,
                )
                run, _ = create_run(
                    session,
                    RunCreate(
                        repo_id="repo-taskboard",
                        conversation_id=conversation.id,
                        task_type=task,
                        target_id=target,
                        question=question,
                        use_knowledge=use_knowledge,
                    ),
                    settings,
                    store,
                    "week04-" + uuid4().hex,
                )
                run_id = run.id
            claimed = worker.claim(run_id)
            assert claimed is not None
            worker.execute(*claimed)
            with Session(engine) as session:
                run = session.get(RunRecord, run_id)
                assert run.status == "succeeded", (run.error_code, run.error_message)
                report = require_report(run)
                proof["runs"].append(
                    {
                        "id": str(run.id),
                        "task_type": task,
                        "use_knowledge": use_knowledge,
                        "url": f"http://127.0.0.1:3000/runs/{run.id}",
                        "result": run.result,
                    }
                )
                output = (
                    Path(args.output).parent
                    / f"week04-{settings.model_provider}-{task}-{use_knowledge}.md"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(report_markdown(report, run.result, str(run.id)).encode())
        Path(args.output).write_bytes(
            (json.dumps(proof, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n").encode()
        )
        print(
            json.dumps(
                {
                    "output": args.output,
                    "documents": len(proof["documents"]),
                    "runs": [
                        {k: v for k, v in item.items() if k != "result"} for item in proof["runs"]
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
