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
    if saved is None:
        raise DomainError(409, "artifact_missing", "证据的原始制品记录缺失")
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


def operation(worker, run_id, token, name, args, *, mcp_client=None):
    """证据和可见结果一次提交；恢复只回放，不重新搜索网络或分支。"""
    from devflow.analysis.tool_gateway import call_fingerprint

    key = "code-tool:" + call_fingerprint(name, args.model_dump_json())

    def guard():
        return worker.guard(run_id, token)

    guard()
    started = time.monotonic()
    with Session(worker.engine) as session:
        run = session.get(RunRecord, run_id)
        sid = bound_snapshot(session, run, args.commit)
        saved = session.get(RunJournal, (run_id, key))
        failed = session.get(RunJournal, (run_id, key + ":error"))
        result = saved.payload if saved else None
        repo_id = run.repo_id
        use_mcp = run.configuration.get("code_backend") == "mcp-stdio-v1"
        previous_meta = session.get(RunJournal, (run_id, key + ":mcp"))
        previous_meta = previous_meta.payload if previous_meta else None
        failed = failed.payload if failed else None
    own_client = False
    if use_mcp and mcp_client is None:
        from devflow.code.mcp_client import CodeMCPClient

        mcp_client = CodeMCPClient(worker, run_id, token)
        own_client = True
    if failed:
        error = DomainError(failed["status"], failed["code"], failed["message"])
        if mcp_client:
            mcp_client.record(name, args, replay=True, error=error, metadata=failed.get("mcp"))
        raise error
    if result is None:
        try:
            if use_mcp:
                result = mcp_client.call(name, args.model_dump())
                with Session(worker.engine) as session:
                    validate_material(session, worker.store, repo_id, sid, name, args, result)
            else:
                with Session(worker.engine) as session:
                    if name == "list_code_tree":
                        result = service.tree(
                            session, repo_id, sid, args.path, args.offset, args.limit
                        )
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
                            session,
                            repo_id,
                            sid,
                            args.path,
                            args.start_line,
                            args.limit,
                            worker.store,
                        )
        except DomainError as error:
            if use_mcp:
                if error.code == "mcp_result_invalid":
                    mcp_client.fail(error)
                with Session(worker.engine) as session, session.begin():
                    worker._owned(session, run_id, token)
                    if session.get(RunJournal, (run_id, key + ":error")) is None:
                        session.add(
                            RunJournal(
                                run_id=run_id,
                                key=key + ":error",
                                payload={
                                    "status": error.status,
                                    "code": error.code,
                                    "message": error.message,
                                    "mcp": dict(mcp_client.info),
                                },
                            )
                        )
                mcp_client.record(
                    name, args, error=error, elapsed_ms=round((time.monotonic() - started) * 1000)
                )
            raise
        finally:
            if own_client:
                mcp_client.close()
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
            if use_mcp:
                session.add(
                    RunJournal(run_id=run_id, key=key + ":mcp", payload=dict(mcp_client.info))
                )
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
    if use_mcp:
        mcp_client.record(
            name,
            args,
            replay=saved is not None,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            result_chars=len(json.dumps(result, ensure_ascii=False)),
            metadata=previous_meta,
            result=result,
        )
    return {**result, "_evidence": evidence_items}


def validate_material(session, store, repo_id, sid, name, args, result):
    """Host 再核对证据来源及实际正文；MCP 服务无权创建任务证据。"""
    from devflow.code.capture import text_lines
    from devflow.storage.models import CodeFile

    meta = service.snapshot(session, repo_id, sid)
    if (
        result.get("repo_id") != repo_id
        or result.get("commit") != args.commit
        or result.get("snapshot_id") != str(sid)
        or result.get("manifest_sha256") != meta.manifest_sha256
    ):
        raise DomainError(502, "mcp_result_invalid", "MCP 结果的仓库、提交或快照哈希不匹配")
    if result["coverage"] != meta.coverage or result["policy_version"] != meta.policy_version:
        raise DomainError(502, "mcp_result_invalid", "MCP 返回的快照覆盖范围或策略不匹配")
    if name == "list_code_tree":
        from devflow.code.schemas import CodeTreeResponse

        expected = CodeTreeResponse.model_validate(
            service.tree(session, repo_id, sid, args.path, args.offset, args.limit)
        ).model_dump(mode="json")
        if result != redact(expected):
            raise DomainError(502, "mcp_result_invalid", "MCP 目录结果路径不匹配")
        return
    fragments = result["items"] if name == "search_code" else [result]
    if name == "search_code" and (
        result["query"] != args.query or result["mode"] != args.mode or len(fragments) > args.limit
    ):
        raise DomainError(502, "mcp_result_invalid", "MCP 搜索参数或结果数量不匹配")
    for fragment in fragments:
        file = session.get(CodeFile, (sid, fragment["path"]))
        if (
            file is None
            or file.skip_reason
            or file.content_sha256 != fragment["content_sha256"]
            or file.blob_sha != fragment["blob_sha"]
            or file.line_count != fragment["line_count"]
            or file.size_bytes != fragment["size_bytes"]
        ):
            raise DomainError(502, "mcp_result_invalid", "MCP 返回了未采集文件或错误的文件哈希")
        if name == "read_file" and (
            fragment["path"] != args.path
            or fragment["start_line"] != args.start_line
            or len(fragment["lines"]) > args.limit
        ):
            raise DomainError(502, "mcp_result_invalid", "MCP 文件读取范围不匹配")
        if name == "search_code":
            if args.mode == "paths" and fragment.get("lines") is not None:
                raise DomainError(502, "mcp_result_invalid", "路径搜索不能返回正文")
            if args.mode == "snippets" and (
                not fragment.get("lines")
                or not fragment["start_line"] <= fragment["match_line"] <= fragment["end_line"]
            ):
                raise DomainError(502, "mcp_result_invalid", "搜索命中行不在返回片段中")
        if fragment.get("lines"):
            _, _, content = service.raw_file(session, repo_id, sid, fragment["path"], store)
            lines = text_lines(content.encode())
            start, end = fragment["start_line"], fragment["end_line"]
            if not 1 <= start <= end <= len(lines) or end - start + 1 != len(fragment["lines"]):
                raise DomainError(502, "mcp_result_invalid", "MCP 返回的行范围无效")
            expected = [
                {"line": number, "text": lines[number - 1]} for number in range(start, end + 1)
            ]
            if redact(expected) != fragment["lines"]:
                raise DomainError(502, "mcp_result_invalid", "MCP 返回正文与本地固定制品不一致")
