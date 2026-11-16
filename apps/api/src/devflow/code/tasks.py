# 文件用途：任务固定代码范围、原子证据绑定与已保存工具结果回放。
import json
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from devflow.code import service
from devflow.core.errors import DomainError
from devflow.core.security import redact
from devflow.storage.models import (
    ArtifactRecord,
    EvidenceRecord,
    ResourceSnapshot,
    RunEvidenceRecord,
    RunJournal,
    RunRecord,
)


def prepare_run(worker, run_id, token):
    def guard():
        return worker.guard(run_id, token)

    with Session(worker.engine) as session:
        run = session.get(RunRecord, run_id)
        access = run.input_version.get("code_access")
        if not access or worker._journal_read(run_id, "code-prepared"):
            return
        repo_id = run.repo_id
        commits = access["allowed_commits"]
    worker._event(run_id, token, "stage.started", {"stage": "code", "label": "准备固定提交代码"})
    deadline = time.monotonic() + worker.settings.code_prepare_seconds
    bindings = []
    for commit in commits:
        guard()
        with Session(worker.engine, expire_on_commit=False) as session, session.begin():
            row = service.request_snapshot(session, repo_id, commit)
            sid = row.id
        while True:
            guard()
            with Session(worker.engine) as session:
                row = service.snapshot(session, repo_id, sid, ready=False)
                data = service.describe(row)
            if row.status in {"ready", "partial", "failed"}:
                break
            if time.monotonic() >= deadline:
                data = {
                    **data,
                    "status": "failed",
                    "error_code": "code_prepare_timeout",
                    "error_message": "本任务代码准备超时，继续使用原有证据",
                }
                break
            ran = service.prepare(
                worker.engine,
                worker.settings,
                worker.store,
                sid,
                client_factory=worker.client_factory,
                guard=guard,
                deadline=deadline,
            )
            if not ran:
                worker.stop.wait(0.1)
        bindings.append(data)
    with Session(worker.engine) as session, session.begin():
        run, _ = worker._owned(session, run_id, token)
        session.add(RunJournal(run_id=run_id, key="code-prepared", payload={"snapshots": bindings}))
    worker._event(
        run_id,
        token,
        "stage.completed",
        {
            "stage": "code",
            "label": "固定代码准备结束",
            "snapshots": bindings,
            "degraded": any(row["status"] not in {"ready", "partial"} for row in bindings),
        },
    )


def analysis_version(session, run):
    version = dict(run.input_version)
    prepared = session.get(RunJournal, (run.id, "code-prepared"))
    if prepared and "code_access" in version:
        access = dict(version["code_access"])
        access.setdefault("snapshots", prepared.payload["snapshots"])
        version["code_access"] = access
    return version


def bound_snapshot(session, run, commit):
    access = analysis_version(session, run).get("code_access", {})
    if commit not in access.get("allowed_commits", []):
        raise DomainError(403, "code_commit_denied", "只能访问本任务允许的完整提交")
    row = next((row for row in access.get("snapshots", []) if row["commit"] == commit), None)
    if not row or row["status"] not in {"ready", "partial"}:
        raise DomainError(
            409, "code_snapshot_not_ready", "本任务的该提交未准备好；不会替换为最新材料"
        )
    return uuid.UUID(row["snapshot_id"])


def bind_file(session, run, sid, path):
    meta = service.snapshot(session, run.repo_id, sid)
    from devflow.storage.models import CodeFile

    file = session.get(CodeFile, (sid, path))
    resource = session.scalar(
        select(ResourceSnapshot).where(
            ResourceSnapshot.repo_id == run.repo_id,
            ResourceSnapshot.kind == "code_snapshot",
            ResourceSnapshot.external_id == str(sid),
        )
    )
    if resource is None:
        resource = ResourceSnapshot(
            repo_id=run.repo_id,
            kind="code_snapshot",
            external_id=str(sid),
            content_sha256=meta.manifest_sha256,
            payload=service.describe(meta),
            is_current=True,
        )
        session.add(resource)
        session.flush()
    evidence = session.scalar(
        select(EvidenceRecord).where(
            EvidenceRecord.resource_snapshot_id == resource.id,
            EvidenceRecord.path == path,
            EvidenceRecord.version == meta.commit_sha,
        )
    )
    if evidence is None:
        evidence = EvidenceRecord(
            repo_id=run.repo_id,
            resource_snapshot_id=resource.id,
            artifact_id=file.artifact_id,
            source_type="file",
            path=path,
            version=meta.commit_sha,
            start_line=1,
            end_line=max(1, file.line_count),
            retrieved_at=meta.updated_at,
        )
        session.add(evidence)
        session.flush()
    if session.get(RunEvidenceRecord, (run.id, evidence.id)) is None:
        session.add(RunEvidenceRecord(run_id=run.id, repo_id=run.repo_id, evidence_id=evidence.id))
    return evidence


def load_evidence(session, evidence, store):
    saved = session.get(ArtifactRecord, evidence.artifact_id)
    return {
        "id": str(evidence.id),
        "artifact_id": str(saved.id),
        "source_type": "file",
        "path": evidence.path,
        "version": evidence.version,
        "start_line": evidence.start_line,
        "end_line": evidence.end_line,
        "content": store.read_text(saved.storage_key, saved.sha256),
    }


def operation(worker, run_id, token, name, args):
    """证据和可见结果一次提交；恢复只回放，不重新搜索网络或分支。"""
    from devflow.analysis.tool_gateway import call_fingerprint

    key = "code-tool:" + call_fingerprint(name, args.model_dump_json())

    def guard():
        return worker.guard(run_id, token)

    guard()
    # 读取和搜索阶段不持有任务行锁，取消及心跳不被搜索阻塞。
    with Session(worker.engine) as session:
        run = session.get(RunRecord, run_id)
        sid = bound_snapshot(session, run, args.commit)
        saved = session.get(RunJournal, (run_id, key))
        result = saved.payload if saved else None
        repo_id = run.repo_id
        if result is None:
            if name == "list_code_tree":
                result = service.tree(session, repo_id, sid, args.path, args.offset, args.limit)
            elif name == "search_code":
                result = service.search(
                    session,
                    repo_id,
                    sid,
                    args.query,
                    args.limit,
                    args.mode,
                    worker.store,
                    worker.settings,
                    guard,
                )
            else:
                result = service.read_file(
                    session, repo_id, sid, args.path, args.start_line, args.limit, worker.store
                )
    with Session(worker.engine) as session, session.begin():
        run, _ = worker._owned(session, run_id, token)
        saved = session.get(RunJournal, (run_id, key))
        if saved:
            result = saved.payload
        else:
            # 先预留引用元数据空间，截掉的片段不建立正文已读记录。
            result = dict(result)
            if name in {"search_code", "list_code_tree"}:
                result["items"] = list(result["items"])
                while result["items"] and len(json.dumps(result, ensure_ascii=False)) > 10000:
                    result["items"].pop()
                    result.update(truncated=True, truncation_reason="output_limit")
            fragments = (
                result.get("items", [])
                if name == "search_code"
                else [result]
                if name == "read_file"
                else []
            )
            for fragment in fragments:
                if not fragment.get("lines"):
                    continue
                evidence = bind_file(session, run, sid, fragment["path"])
                fragment.update(
                    id=str(evidence.id),
                    artifact_id=str(evidence.artifact_id),
                    full_artifact_id=str(evidence.artifact_id),
                    source_type="file",
                    version=args.commit,
                    stored_range=[1, evidence.end_line],
                )
            while result.get("items") and len(json.dumps(result, ensure_ascii=False)) > 11500:
                result["items"].pop()
                result.update(
                    truncated=True, truncation_reason="output_limit", search_complete=False
                )
            if name == "list_code_tree" and result.get("truncated"):
                result["next_offset"] = args.offset + len(result["items"])
            if len(json.dumps(result, ensure_ascii=False)) > 11500:
                raise DomainError(
                    413, "tool_result_too_large", "片段元数据超过限额，请缩小读取范围"
                )
            result = redact(result)
            session.add(RunJournal(run_id=run_id, key=key, payload=result))
        fragments = (
            result.get("items", [])
            if name == "search_code"
            else [result]
            if name == "read_file"
            else []
        )
        evidence_items = []
        for fragment in fragments:
            if fragment.get("id"):
                evidence = session.get(EvidenceRecord, uuid.UUID(fragment["id"]))
                if (
                    evidence is None
                    or evidence.repo_id != run.repo_id
                    or session.get(RunEvidenceRecord, (run.id, evidence.id)) is None
                ):
                    raise DomainError(409, "code_evidence_missing", "保存的代码证据关联已缺失")
                evidence_items.append(load_evidence(session, evidence, worker.store))
    return {**result, "_evidence": evidence_items}
