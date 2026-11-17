# 文件用途：代码快照队列、不可变发布、目录与片段访问，以及固定参数 ripgrep 搜索。
import hashlib
import json
import logging
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from devflow.code.capture import collect, text_lines
from devflow.core.errors import DomainError
from devflow.repositories.github_client import GitHubClient
from devflow.storage.models import ArtifactRecord, CodeFile, CodeSnapshot, RepositoryRecord

POLICY = "code-text-v1"
SEARCH_SECONDS = 5.0
logger = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def rg_path(settings):
    value = shutil.which(settings.code_rg_path.strip() or "rg")
    return str(Path(value).resolve()) if value else None


def repository(session, repo_id):
    repo = session.get(RepositoryRecord, repo_id)
    if repo is None:
        raise DomainError(404, "repository_not_found", "仓库未导入")
    return repo


def request_snapshot(session, repo_id, commit=None, *, retry=False):
    repo = repository(session, repo_id)
    commit = commit or repo.default_commit
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DomainError(422, "invalid_commit", "必须使用完整提交 SHA")
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(repo_id + commit, 75))))
    row = session.scalar(
        select(CodeSnapshot)
        .where(
            CodeSnapshot.repo_id == repo_id,
            CodeSnapshot.commit_sha == commit,
            CodeSnapshot.policy_version == POLICY,
        )
        .with_for_update()
    )
    if row is None:
        row = CodeSnapshot(repo_id=repo_id, commit_sha=commit, policy_version=POLICY, coverage={})
        session.add(row)
        session.flush()
    elif retry and row.status == "failed":
        row.status, row.error_code, row.error_message = "queued", None, None
    return row


def cached_snapshot(session, repo_id, commit=None):
    """只查本地清单；浏览页面不发准备请求，也不访问 GitHub。"""
    repo = repository(session, repo_id)
    query = select(CodeSnapshot).where(
        CodeSnapshot.repo_id == repo_id, CodeSnapshot.policy_version == POLICY
    )
    if commit:
        return session.scalar(query.where(CodeSnapshot.commit_sha == commit))
    pinned = (repo.sync_state or {}).get("code_workspace", {}).get("snapshot_id")
    if pinned:
        row = session.get(CodeSnapshot, uuid.UUID(pinned))
        if row and row.repo_id == repo_id and row.status in {"ready", "partial"}:
            return row
    row = session.scalar(
        query.where(CodeSnapshot.status.in_(["ready", "partial"]))
        .order_by(
            (CodeSnapshot.commit_sha == repo.default_commit).desc(),
            CodeSnapshot.updated_at.desc(),
            CodeSnapshot.id.desc(),
        )
        .limit(1)
    )
    return row or session.scalar(
        query.order_by(CodeSnapshot.created_at.desc(), CodeSnapshot.id.desc()).limit(1)
    )


def select_for_browsing(session, row, *, requested=False):
    repo = session.scalar(
        select(RepositoryRecord)
        .where(RepositoryRecord.id == row.repo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    state = dict(repo.sync_state or {})
    workspace = dict(state.get("code_workspace", {}))
    if requested:
        workspace["requested_snapshot_id"] = str(row.id)
    if workspace.get("requested_snapshot_id") == str(row.id) and row.status in {"ready", "partial"}:
        workspace["snapshot_id"] = str(row.id)
    if workspace:
        repo.sync_state = {**state, "code_workspace": workspace}


def pull_latest(session, repo_id, settings, *, client_factory=GitHubClient):
    """显式拉取才解析远端默认分支；相同 SHA 复用已发布快照。"""
    from devflow.repositories.github_client import ref_path, repo_path

    repo = repository(session, repo_id)
    commit, branch = repo.default_commit, repo.default_branch
    if repo.data_source == "github":
        client = client_factory(settings)
        root = repo_path(repo.full_name)
        metadata = client.get(root)
        branch = metadata.get("default_branch")
        if not isinstance(branch, str) or not branch:
            raise DomainError(502, "github_invalid_response", "GitHub 未返回默认分支")
        commit = client.get(root + "/commits/" + ref_path(branch)).get("sha")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise DomainError(502, "github_invalid_response", "GitHub 未返回完整提交 SHA")
    row = request_snapshot(session, repo_id, commit, retry=True)
    select_for_browsing(session, row, requested=True)
    repo.default_commit, repo.default_branch = commit, branch
    return row


def snapshot(session, repo_id, snapshot_id, *, ready=True):
    repository(session, repo_id)
    row = session.get(CodeSnapshot, snapshot_id)
    if row is None or row.repo_id != repo_id:
        raise DomainError(404, "code_snapshot_not_found", "代码快照不存在或不属于当前仓库")
    if ready and row.status not in {"ready", "partial"}:
        raise DomainError(
            409, "code_snapshot_not_ready", row.error_message or "代码快照尚未准备完成"
        )
    return row


def describe(row):
    return {
        "snapshot_id": str(row.id),
        "repo_id": row.repo_id,
        "commit": row.commit_sha,
        "policy_version": row.policy_version,
        "status": row.status,
        "manifest_sha256": row.manifest_sha256,
        "coverage": row.coverage,
        "error_code": row.error_code,
        "error_message": row.error_message,
    }


def artifact(session, repo_id, raw, store):
    key, sha, size = store.put_bytes(raw)
    row = session.scalar(
        select(ArtifactRecord).where(
            ArtifactRecord.repo_id == repo_id, ArtifactRecord.sha256 == sha
        )
    )
    if row is None:
        row = ArtifactRecord(
            repo_id=repo_id,
            sha256=sha,
            size_bytes=size,
            media_type="text/plain; charset=utf-8",
            storage_key=key,
        )
        session.add(row)
        session.flush()
    return row


def prepare(
    engine,
    settings,
    store,
    snapshot_id=None,
    *,
    client_factory=GitHubClient,
    guard=lambda: None,
    deadline=None,
):
    """队列及分析共用领取流程；租约每次操作续期，发布再次校验令牌。"""
    deadline = min(deadline or float("inf"), time.monotonic() + settings.code_prepare_seconds)
    with Session(engine, expire_on_commit=False) as session, session.begin():
        now = session.scalar(select(func.clock_timestamp()))
        row = session.scalar(
            select(CodeSnapshot)
            .where(
                or_(
                    CodeSnapshot.status == "queued",
                    (CodeSnapshot.status == "preparing") & (CodeSnapshot.lease_expires_at <= now),
                ),
                CodeSnapshot.id == snapshot_id if snapshot_id else True,
            )
            .order_by(CodeSnapshot.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return False
        token, sid, repo_id, commit = uuid.uuid4(), row.id, row.repo_id, row.commit_sha
        row.status, row.lease_token = "preparing", token
        row.error_code = row.error_message = None
        row.lease_expires_at = now + timedelta(seconds=45)
        repo = repository(session, repo_id)
    last_pulse = 0

    def pulse():
        nonlocal last_pulse
        guard()
        if time.monotonic() >= deadline:
            raise DomainError(504, "code_prepare_timeout", "代码准备达到时长上限")
        if time.monotonic() - last_pulse < 2:
            return
        with Session(engine) as session, session.begin():
            live = session.scalar(
                select(CodeSnapshot).where(CodeSnapshot.id == sid).with_for_update()
            )
            now = session.scalar(select(func.clock_timestamp()))
            if (
                live.lease_token != token
                or live.status != "preparing"
                or live.lease_expires_at <= now
            ):
                raise DomainError(409, "code_lease_lost", "代码快照准备租约已失效")
            live.lease_expires_at = now + timedelta(seconds=45)
        last_pulse = time.monotonic()

    started = time.monotonic()
    try:
        pulse()
        client = client_factory(settings)
        if hasattr(client, "deadline"):
            client.deadline = deadline
        rows, contents, coverage = collect(repo, commit, client, settings, pulse)
        pulse()
        with Session(engine) as session, session.begin():
            live = session.scalar(
                select(CodeSnapshot).where(CodeSnapshot.id == sid).with_for_update()
            )
            now = session.scalar(select(func.clock_timestamp()))
            if (
                live.lease_token != token
                or live.status != "preparing"
                or live.lease_expires_at <= now
            ):
                raise DomainError(409, "code_lease_lost", "代码快照准备租约已失效")
            session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(repo_id, 42))))
            manifest = []
            for item in rows:
                guard()
                raw = contents.get(item["path"])
                saved = artifact(session, repo_id, raw, store) if raw is not None else None
                entry = CodeFile(
                    snapshot_id=sid,
                    repo_id=repo_id,
                    **item,
                    artifact_id=saved.id if saved else None,
                    content_sha256=saved.sha256 if saved else None,
                    line_count=len(text_lines(raw)) if raw is not None else 0,
                )
                session.add(entry)
                manifest.append(
                    {**item, "content_sha256": entry.content_sha256, "line_count": entry.line_count}
                )
            if time.monotonic() >= deadline:
                raise DomainError(504, "code_prepare_timeout", "代码准备达到时长上限")
            live.manifest_sha256 = digest(manifest)
            live.coverage = {**coverage, "duration_ms": round((time.monotonic() - started) * 1000)}
            live.status = "ready" if coverage["eligible_complete"] else "partial"
            live.lease_token = live.lease_expires_at = None
            live.updated_at = now
            select_for_browsing(session, live)
        logger.info(
            "code_snapshot ready=%s files=%s bytes=%s duration_ms=%s",
            sid,
            coverage["saved_files"],
            coverage["saved_bytes"],
            round((time.monotonic() - started) * 1000),
        )
    except BaseException as error:
        with Session(engine) as session, session.begin():
            live = session.scalar(
                select(CodeSnapshot).where(CodeSnapshot.id == sid).with_for_update()
            )
            if live.lease_token == token:
                interrupted = type(error).__name__ in {
                    "LeaseLost",
                    "RunCancelled",
                    "RunTimedOut",
                } or not isinstance(error, Exception)
                live.status = "queued" if interrupted else "failed"
                live.error_code = (
                    error.code if isinstance(error, DomainError) else "code_prepare_failed"
                )
                live.error_message = (
                    error.message
                    if isinstance(error, DomainError)
                    else "代码准备失败，请重试并检查服务日志"
                )
                live.lease_token = live.lease_expires_at = None
                live.updated_at = session.scalar(select(func.clock_timestamp()))
        if type(error).__name__ in {"LeaseLost", "RunCancelled", "RunTimedOut"} or not isinstance(
            error, Exception
        ):
            raise
        logger.warning("code_snapshot failed=%s error_type=%s", sid, type(error).__name__)
    return True


def file_descriptor(row):
    return {
        key: getattr(row, key)
        for key in (
            "path",
            "kind",
            "blob_sha",
            "content_sha256",
            "size_bytes",
            "line_count",
            "skip_reason",
        )
    }


def tree(session, repo_id, sid, path="", offset=0, limit=100):
    meta = snapshot(session, repo_id, sid)
    if path:
        from devflow.repositories.fixed_files import safe_path

        safe_path(path)
    prefix = path + "/" if path else ""
    files = session.scalars(
        select(CodeFile).where(CodeFile.snapshot_id == sid).order_by(CodeFile.path)
    ).all()
    children = {}
    for item in files:
        if not item.path.startswith(prefix):
            continue
        rest = item.path[len(prefix) :]
        if "/" in rest:
            name = prefix + rest.split("/", 1)[0]
            children[name] = {"path": name, "kind": "directory", "skip_reason": None}
        else:
            children[item.path] = file_descriptor(item)
    values = sorted(
        children.values(), key=lambda value: (value["kind"] != "directory", value["path"])
    )
    return {
        **describe(meta),
        "path": path,
        "items": values[offset : offset + limit],
        "next_offset": offset + limit if offset + limit < len(values) else None,
    }


def raw_file(session, repo_id, sid, path, store):
    from devflow.repositories.fixed_files import safe_path

    safe_path(path)
    meta = snapshot(session, repo_id, sid)
    row = session.get(CodeFile, (sid, path))
    if row is None:
        raise DomainError(404, "code_file_not_found", "文件不在此快照的已知清单中，请检查覆盖范围")
    if row.skip_reason:
        raise DomainError(409, "code_file_skipped", "文件未纳入读取范围：" + row.skip_reason)
    saved = session.get(ArtifactRecord, row.artifact_id)
    if saved is None:
        raise DomainError(409, "artifact_missing", "文件的原始制品记录缺失")
    # read_text 校验的是原始字节，显示及搜索统一去除 BOM 并按原始行划分。
    content = store.read_text(saved.storage_key, saved.sha256).removeprefix("\ufeff")
    return meta, row, content


def read_file(session, repo_id, sid, path, start, limit, store):
    meta, row, content = raw_file(session, repo_id, sid, path, store)
    lines = text_lines(content.encode())
    if start < 1 or start > len(lines):
        raise DomainError(422, "invalid_line_range", "起始行超出文件范围")
    result, size = [], 0
    for index in range(start - 1, min(len(lines), start - 1 + limit)):
        if size + len(lines[index]) > 7000:
            if not result:
                raise DomainError(413, "tool_line_too_long", "单行超过片段读取上限")
            break
        result.append({"line": index + 1, "text": lines[index]})
        size += len(lines[index])
    end = result[-1]["line"]
    return {
        **describe(meta),
        **file_descriptor(row),
        "start_line": start,
        "end_line": end,
        "lines": result,
        "next_line": end + 1 if end < len(lines) else None,
        "redaction_note": "正文按规则脱敏，哈希对应原始制品",
    }


def search(
    session,
    repo_id,
    sid,
    query,
    limit,
    mode,
    store,
    settings,
    guard=lambda: None,
    timeout_seconds=None,
):
    search_seconds = (
        SEARCH_SECONDS if timeout_seconds is None else min(SEARCH_SECONDS, timeout_seconds)
    )
    meta = snapshot(session, repo_id, sid)
    if not 1 <= len(query) <= 500 or any(c in query for c in "\r\n\0"):
        raise DomainError(422, "invalid_code_query", "查询必须是 1～500 字符的单行字面量")
    executable = rg_path(settings)
    if executable is None:
        raise DomainError(503, "code_search_unavailable", "ripgrep 未就绪，请配置 CODE_RG_PATH")
    started, hits, reason = time.monotonic(), [], None
    files = session.scalars(
        select(CodeFile)
        .where(CodeFile.snapshot_id == sid, CodeFile.artifact_id.is_not(None))
        .order_by(CodeFile.path)
    ).all()
    with tempfile.TemporaryDirectory(prefix="devflow-code-") as directory:
        mapping = {}
        for index, row in enumerate(files):
            guard()
            if time.monotonic() - started >= search_seconds:
                raise DomainError(504, "code_search_timeout", "搜索投影准备超时，未执行完整搜索")
            _, _, content = raw_file(session, repo_id, sid, row.path, store)
            name = f"f{index:06d}"
            Path(directory, name).write_bytes("\n".join(text_lines(content.encode())).encode())
            mapping[name] = row
        process = subprocess.Popen(
            [
                executable,
                "--json",
                "--fixed-strings",
                "--case-sensitive",
                "--no-config",
                "--no-ignore",
                "--hidden",
                "--sort",
                "path",
                "--color",
                "never",
                "--encoding",
                "utf-8",
                "--",
                query,
                ".",
            ],
            cwd=directory,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        events = queue.Queue(maxsize=64)
        stopped = threading.Event()

        def reader():
            try:
                for line in process.stdout:
                    while not stopped.is_set():
                        try:
                            events.put(line, timeout=0.05)
                            break
                        except queue.Full:
                            pass
                    if stopped.is_set():
                        break
            finally:
                while not stopped.is_set():
                    try:
                        events.put(None, timeout=0.05)
                        break
                    except queue.Full:
                        pass

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        try:
            while True:
                guard()
                remaining = search_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    reason = "timeout"
                    break
                try:
                    line = events.get(timeout=min(0.1, remaining))
                except queue.Empty:
                    continue
                if line is None:
                    process.wait(timeout=2)
                    break
                event = json.loads(line)
                if event.get("type") != "match":
                    continue
                data = event["data"]
                row = mapping[Path(data["path"]["text"]).name]
                if mode == "paths" and any(item[0].path == row.path for item in hits):
                    continue
                if len(hits) == limit:
                    reason = "result_limit"
                    break
                hits.append((row, data["line_number"]))
        finally:
            stopped.set()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            thread.join(timeout=2)
            process.stdout.close()
        if reason is None and process.returncode not in {0, 1}:
            raise DomainError(502, "code_search_failed", "ripgrep 未完成搜索")
    items = []
    for row, number in hits:
        guard()
        item = file_descriptor(row)
        item["match_line"] = number
        if mode == "snippets":
            try:
                fragment = read_file(session, repo_id, sid, row.path, max(1, number - 3), 7, store)
                item.update({key: fragment[key] for key in ("start_line", "end_line", "lines")})
                if not fragment["start_line"] <= number <= fragment["end_line"]:
                    reason = reason or "line_too_long"
                    continue
            except DomainError as error:
                if error.code != "tool_line_too_long":
                    raise
                reason = reason or "line_too_long"
                continue
        trial = {"items": items + [item]}
        if len(json.dumps(trial, ensure_ascii=False)) > 9000:
            reason = reason or "output_limit"
            break
        items.append(item)
    result = {
        **describe(meta),
        "path": "",
        "query": query,
        "mode": mode,
        "items": items,
        "truncated": reason is not None,
        "truncation_reason": reason,
        "search_complete": reason is None,
    }
    logger.info(
        "code_search snapshot=%s duration_ms=%s matches=%s truncated=%s",
        sid,
        round((time.monotonic() - started) * 1000),
        len(items),
        reason,
    )
    return result
