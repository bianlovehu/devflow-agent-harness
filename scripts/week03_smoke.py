# 文件用途：显式运行第三周 fixture 或真实 GitHub 分析并保存不含密钥的验收摘要。
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from devflow.artifact_store import ArtifactStore
from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.evidence_capture import Captured, bind_capture
from devflow.github_source import GitHubRepositorySource, ci_summary, pull_summary
from devflow.models import RepositoryRecord, RunRecord
from devflow.reports import report_markdown, require_report
from devflow.worker import Worker
from devflow.workflow_contracts import ConversationCreate, RunBudget, RunCreate
from devflow.workflows import create_conversation, create_run
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--github", help="真实仓库 owner/name；省略则使用 fixture")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--ci", type=int)
    parser.add_argument("--fake", action="store_true", help="仅 fixture 可用的离线假模型")
    parser.add_argument("--snapshot", help="从连接器采集的公开固定版本快照验收，不再请求 GitHub")
    parser.add_argument("--output", default="data/week03-proof.json")
    args = parser.parse_args()
    archive = None
    if args.snapshot:
        archive = json.loads(Path(args.snapshot).read_text(encoding="utf-8-sig"))
        if archive["repository"].get("private", True):
            parser.error("此验收入口仅接受公开仓库快照")
        args.github = archive["repository"]["full_name"]
        args.pr = int(archive["external_id"]) if archive["kind"] == "pull_request" else None
        args.ci = int(archive["external_id"]) if archive["kind"] == "ci_run" else None
        for item in archive["sources"]:
            raw = item["content"].encode()
            if item.get("blob_sha"):
                blob_sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
                if blob_sha != item["blob_sha"]:
                    parser.error("固定文件与 GitHub blob SHA 不符")
    settings = get_settings().model_copy(
        update={
            "data_source": "github" if args.github else "fixture",
            "analysis_executor": "agent",
            "simulation_step_seconds": 0,
        }
    )
    if args.fake:
        settings.model_provider = "fake"
    engine, store = create_database_engine(settings), ArtifactStore()
    proof = []
    try:
        repo_id = "repo-taskboard"
        if archive:
            repo_id = f"github-{archive['repository']['id']}"
            with Session(engine) as session, session.begin():
                repo = session.get(RepositoryRecord, repo_id)
                if repo is None or repo.full_name != args.github or repo.data_source != "github":
                    parser.error("请先在应用中登记此公开仓库，再导入验收快照")
                metadata = archive["payload"]["metadata"]
                summary = (
                    pull_summary(metadata, repo_id, datetime.now(UTC))
                    if args.pr
                    else ci_summary(metadata, repo_id, args.github, datetime.now(UTC))
                )
                state = dict(repo.sync_state or {})
                section = dict(state.get(archive["kind"], {}))
                field = "number" if args.pr else "id"
                section["items"] = [
                    summary.model_dump(mode="json"),
                    *[
                        row
                        for row in section.get("items", [])
                        if str(row[field]) != archive["external_id"]
                    ],
                ][:20]
                section["fetched_at"] = archive["payload"]["captured_at"]
                state[archive["kind"]] = section
                repo.sync_state = state
        elif args.github:
            with Session(engine, expire_on_commit=False) as session:
                source = GitHubRepositorySource(session, settings)
                repo_id = source.add_repository("https://github.com/" + args.github).id
        targets = [("pr_review", args.pr or 102), ("ci_debug", args.ci or 201)]
        if args.github:
            targets = [
                (task, target)
                for task, target in [("pr_review", args.pr), ("ci_debug", args.ci)]
                if target
            ]
            if not targets:
                parser.error("--github requires --pr or --ci")
        worker = Worker(engine, settings, store)
        for task, target in targets:
            with Session(engine, expire_on_commit=False) as session:
                conversation = create_conversation(
                    session,
                    ConversationCreate(repo_id=repo_id, title=f"第三周验收 {task} #{target}"),
                    settings,
                )
            with Session(engine, expire_on_commit=False) as session:
                run, _ = create_run(
                    session,
                    RunCreate(
                        repo_id=repo_id,
                        conversation_id=conversation.id,
                        task_type=task,
                        target_id=str(target),
                        question="请根据固定版本证据分析，引用原始行号并说明检查范围。",
                        budget=RunBudget(max_model_calls=8, max_total_tokens=120000),
                    ),
                    settings,
                    store,
                )
                run_id = run.id
            if archive:
                with Session(engine) as session, session.begin():
                    run = session.get(RunRecord, run_id)
                    capture = Captured(
                        archive["kind"],
                        archive["external_id"],
                        archive["payload"],
                        [
                            (
                                item["source_type"],
                                item["path"],
                                item["version"],
                                item["content"].encode(),
                            )
                            for item in archive["sources"]
                        ],
                    )
                    bind_capture(session, run, capture, store)
            claimed = worker.claim(run_id)
            if claimed is None:
                raise RuntimeError(
                    "Smoke run was claimed by another worker; stop background worker first"
                )
            worker.execute(*claimed)
            with Session(engine) as session:
                run = session.get(RunRecord, run_id)
                item = {
                    "run_id": str(run.id),
                    "task_type": task,
                    "target": target,
                    "status": run.status,
                    "error_code": run.error_code,
                    "error_message": run.error_message,
                    "result": run.result,
                }
                proof.append(item)
                if run.status == "succeeded":
                    report = require_report(run)
                    Path(f"data/week03-{run.id}.md").write_text(
                        report_markdown(report, run.result, str(run.id)),
                        encoding="utf-8",
                        newline="",
                    )
                print(
                    json.dumps(
                        {key: value for key, value in item.items() if key != "result"},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(proof, ensure_ascii=False, indent=2).replace("\n", "\r\n") + "\r\n",
            encoding="utf-8",
            newline="",
        )
        raise SystemExit(0 if all(item["status"] == "succeeded" for item in proof) else 1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
