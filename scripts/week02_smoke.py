# 文件用途：在本地数据库执行第二周端到端验收，保存无密钥的任务、事件和证据摘要。
import argparse
import json
import uuid
from pathlib import Path

from devflow.artifact_store import ArtifactStore
from devflow.config import PROJECT_ROOT, get_settings
from devflow.database import create_database_engine
from devflow.github_client import GitHubClient
from devflow.github_source import GitHubRepositorySource
from devflow.models import ArtifactRecord, RunEventRecord, RunRecord
from devflow.worker import Worker
from devflow.workflow_contracts import ConversationCreate, RunCreate
from devflow.workflows import create_conversation, create_run, run_evidence
from sqlalchemy import select
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description="第二周证据与后台通道验收（不调用模型）")
    parser.add_argument("--github", help="显式选择真实 GitHub 仓库，例如 pallets/flask")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data/week02-proof.json")
    args = parser.parse_args()
    settings = get_settings().model_copy(
        update={
            "data_source": "github" if args.github else "fixture",
            "simulation_step_seconds": 0,
            "analysis_executor": "simulation",
        }
    )
    engine = create_database_engine(settings)
    store = ArtifactStore()
    try:
        repo_id, target = "repo-taskboard", "102"
        if args.github:
            with Session(engine, expire_on_commit=False) as session:
                source = GitHubRepositorySource(session, settings)
                repo = source.add_repository(args.github)
                repo_id = repo.id
                candidates = source.list_pull_requests(repo.id)
            if not candidates:
                raise RuntimeError("仓库最近没有 PR，无法进行真实 PR 证据验收")
            # 优先选择文件较少的 PR，使匿名读取规模可控；所有读取仍走 GET。
            client = GitHubClient(settings)
            for item in candidates[:5]:
                detail = client.get(f"/repos/{repo.full_name}/pulls/{item.number}")
                if 0 < detail.get("changed_files", 0) <= 5:
                    target = str(item.number)
                    break
            else:
                target = str(candidates[0].number)
        with Session(engine, expire_on_commit=False) as session:
            conversation = create_conversation(
                session, ConversationCreate(repo_id=repo_id, title="第二周端到端验收"), settings
            )
            run, replayed = create_run(
                session,
                RunCreate(
                    repo_id=repo_id,
                    conversation_id=conversation.id,
                    task_type="pr_review",
                    target_id=target,
                    question="第二周验收：固定证据并验证持久化后台通道，不调用模型。",
                ),
                settings,
                store,
                "week02-" + uuid.uuid4().hex,
            )
            run_id = run.id
        candidate = Worker(engine, settings, store)
        # 正常使用由独立 worker 领取；此命令用于可重跑的单进程验收，并使用相同领取和执行代码。
        for _ in range(100):
            with Session(engine) as session:
                state = session.get(RunRecord, run_id).status
            if state in {"succeeded", "failed", "cancelled", "needs_attention"}:
                break
            if not candidate.run_once():
                raise RuntimeError("验收任务被其他 worker 领取，请待完成后读取任务详情")
        with Session(engine) as session:
            run = session.get(RunRecord, run_id)
            evidence = run_evidence(session, run_id)
            artifacts = []
            for row in evidence:
                artifact = session.get(ArtifactRecord, row.artifact_id)
                store.read_text(artifact.storage_key, artifact.sha256)
                artifacts.append(
                    {
                        "evidence_id": str(row.id),
                        "path": row.path,
                        "version": row.version,
                        "lines": [row.start_line, row.end_line],
                        "sha256": artifact.sha256,
                    }
                )
            events = session.scalars(
                select(RunEventRecord)
                .where(RunEventRecord.run_id == run_id)
                .order_by(RunEventRecord.sequence)
            ).all()
            proof = {
                "run_id": str(run_id),
                "conversation_id": str(conversation.id),
                "repo_id": repo_id,
                "status": run.status,
                "input_version": run.input_version,
                "result": run.result,
                "error_code": run.error_code,
                "error_message": run.error_message,
                "events": [{"sequence": row.sequence, "type": row.event_type} for row in events],
                "evidence": artifacts,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(
                (json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
                .replace("\n", "\r\n")
                .encode()
            )
            print(
                json.dumps(
                    {
                        "run_id": str(run_id),
                        "status": run.status,
                        "evidence": len(evidence),
                        "events": len(events),
                        "proof": str(args.output),
                    },
                    ensure_ascii=False,
                )
            )
            if run.status != "succeeded":
                raise RuntimeError("验收未成功，详情见证明文件")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
