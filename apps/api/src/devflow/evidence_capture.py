# 文件用途：采集并持久化固定提交、diff 和指定 CI attempt 的不可变证据。
import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select, update

from devflow.artifact_store import ArtifactStore
from devflow.errors import DomainError
from devflow.fixed_files import FixedFileReader, safe_path
from devflow.github_client import repo_path
from devflow.import_fixtures import json_digest
from devflow.models import ArtifactRecord, EvidenceRecord, ResourceSnapshot, RunEvidenceRecord

MAX_CAPTURE_FILES = 50
MAX_CAPTURE_JOBS = 20
MAX_CAPTURE_BYTES = 8 * 1024 * 1024


def patch_complete(patch: str | None, additions: int, deletions: int) -> bool:
    if not isinstance(patch, str):
        return False
    plus = minus = 0
    expected_old = expected_new = actual_old = actual_new = 0
    hunk = False
    for line in patch.splitlines():
        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if match:
            if hunk and (actual_old != expected_old or actual_new != expected_new):
                return False
            expected_old = int(match[2]) if match[2] is not None else 1
            expected_new = int(match[4]) if match[4] is not None else 1
            actual_old = actual_new = 0
            hunk = True
        elif hunk and line.startswith("+"):
            plus += 1
            actual_new += 1
        elif hunk and line.startswith("-"):
            minus += 1
            actual_old += 1
        elif hunk and line.startswith(" "):
            actual_old += 1
            actual_new += 1
        elif line.startswith("\\ No newline"):
            pass
        else:
            return False
    return (
        plus == additions
        and minus == deletions
        and (not hunk or (actual_old == expected_old and actual_new == expected_new))
    )


@dataclass
class Captured:
    kind: str
    external_id: str
    payload: dict
    # (source type, display path, immutable version, original bytes)
    sources: list[tuple[str, str, str, bytes]] = field(default_factory=list)


def capture_github(
    full_name: str, resource: dict, client, guard=lambda: None, *, include_context=False
) -> Captured:
    root = repo_path(full_name)
    kind = resource["kind"]
    target = int(resource["external_id"])
    payload = {
        **resource,
        "captured_at": datetime.now(UTC).isoformat(),
        "coverage": [],
        "warnings": [],
    }
    captured = Captured(kind, str(target), payload)
    total_bytes = 0

    def add(source_type, path, version, raw):
        nonlocal total_bytes
        if total_bytes + len(raw) > MAX_CAPTURE_BYTES:
            raise DomainError(413, "evidence_budget_exceeded", "本次证据超过 8 MiB 上限")
        captured.sources.append((source_type, path, version, raw))
        total_bytes += len(raw)

    def warn(path, error):
        payload["warnings"].append({"path": path, "code": error.code, "message": error.message})

    if kind == "pull_request":

        def verify():
            guard()
            pr = client.get(f"{root}/pulls/{target}")
            if (
                pr["base"]["sha"] != resource["base_sha"]
                or pr["head"]["sha"] != resource["head_sha"]
            ):
                raise DomainError(409, "input_changed", "PR 版本已变化，请刷新仓库后创建新任务")
            return pr

        pr = verify()
        files, limited = client.paginate(f"{root}/pulls/{target}/files", limit=300)
        payload["files_limited"] = limited or pr.get("changed_files", len(files)) > len(files)
        payload["changed_files"] = pr.get("changed_files", len(files))
        payload["metadata"] = pr
        reader = FixedFileReader(client, full_name)
        for item in files[:MAX_CAPTURE_FILES]:
            guard()
            path = safe_path(item["filename"])
            old_path = safe_path(item.get("previous_filename") or path)
            row = {
                "path": path,
                "previous_path": old_path,
                "status": item["status"],
                "patch_complete": patch_complete(
                    item.get("patch"), item.get("additions", 0), item.get("deletions", 0)
                ),
                "base_saved": False,
                "head_saved": False,
                "supplemented": False,
            }
            payload["coverage"].append(row)
            if item.get("patch") is not None:
                add(
                    "diff",
                    path + ".diff",
                    resource["base_sha"] + ".." + resource["head_sha"],
                    item["patch"].encode(),
                )
            contents = {}
            for side, file_path, absent in (
                ("base", old_path, item["status"] == "added"),
                ("head", path, item["status"] == "removed"),
            ):
                if absent:
                    contents[side] = b""
                    row[side + "_absent"] = True
                    continue
                try:
                    guard()
                    raw = reader.read(resource[side + "_sha"], file_path)
                    add("file", file_path, resource[side + "_sha"], raw)
                    contents[side] = raw
                    row[side + "_saved"] = True
                except DomainError as error:
                    warn(file_path + ":" + side, error)
            if not row["patch_complete"] and len(contents) == 2:
                # 缺失或截断 patch 时，以两个已固定版本生成完整补充 diff。
                diff_lines = list(
                    difflib.unified_diff(
                        contents["base"].decode("utf-8-sig").splitlines(keepends=True),
                        contents["head"].decode("utf-8-sig").splitlines(keepends=True),
                        fromfile="a/" + old_path,
                        tofile="b/" + path,
                    )
                )
                diff = "".join(
                    line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                    for line in diff_lines
                )
                add(
                    "diff",
                    path + ".complete.diff",
                    resource["base_sha"] + ".." + resource["head_sha"],
                    diff.encode(),
                )
                row["supplemented"] = True
        payload["files_limited"] |= len(files) > MAX_CAPTURE_FILES
        if include_context:
            # 关联资料只在采集时读取，后续工具使用保存的固定材料，不追随远端变化。
            issue_numbers = list(
                dict.fromkeys(re.findall(r"(?<![\w/])#([1-9][0-9]*)", pr.get("body") or ""))
            )[:5]
            for number in issue_numbers:
                guard()
                try:
                    issue = client.get(f"{root}/issues/{number}")
                    text = json.dumps(
                        {
                            key: issue.get(key)
                            for key in ("number", "title", "body", "state", "updated_at")
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    add("issue", f"issues/{number}.json", json_digest(issue), text.encode())
                except DomainError as error:
                    warn(f"issue/{number}", error)
            guard()
            try:
                runs, limited = client.paginate(
                    f"{root}/actions/runs",
                    key="workflow_runs",
                    limit=2,
                    params={"head_sha": resource["head_sha"]},
                )
                payload["related_ci_limited"] = limited
                payload["related_ci"] = []
                for run in runs[:1]:
                    if run["head_sha"] != resource["head_sha"]:
                        continue
                    guard()
                    ci = capture_github(
                        full_name,
                        {
                            "kind": "ci_run",
                            "external_id": str(run["id"]),
                            "head_sha": run["head_sha"],
                            "run_attempt": run.get("run_attempt", 1),
                        },
                        client,
                        guard,
                    )
                    for source_type, path, version, raw in ci.sources:
                        add(source_type, path, version, raw)
                    payload["related_ci"].append(
                        {
                            "id": run["id"],
                            "run_attempt": run.get("run_attempt", 1),
                            "conclusion": run.get("conclusion"),
                        }
                    )
                    payload["warnings"].extend(ci.payload["warnings"])
            except DomainError as error:
                warn("related-ci", error)
        verify()  # 文件列表不接受 ref；采集前后检查 PR，拒绝混合两个版本的材料。
    elif kind == "ci_run":
        guard()
        attempt = resource["run_attempt"]
        run = client.get(f"{root}/actions/runs/{target}/attempts/{attempt}")
        if run["head_sha"] != resource["head_sha"] or run.get("run_attempt") != attempt:
            raise DomainError(409, "input_changed", "CI attempt 与固定输入不一致")
        payload["metadata"] = run
        jobs, limited = client.paginate(
            f"{root}/actions/runs/{target}/attempts/{attempt}/jobs", key="jobs", limit=200
        )
        payload["jobs_limited"] = limited or len(jobs) > MAX_CAPTURE_JOBS
        # 优先保留失败 job，避免大量成功矩阵任务耗尽日志采集上限。
        jobs.sort(key=lambda job: job.get("conclusion") not in {"failure", "timed_out"})
        for job in jobs[:MAX_CAPTURE_JOBS]:
            guard()
            row = {
                "job_id": job["id"],
                "name": job["name"],
                "status": job["status"],
                "conclusion": job.get("conclusion"),
                "steps": [
                    {key: step.get(key) for key in ("number", "name", "conclusion")}
                    for step in job.get("steps", [])
                ],
                "log_saved": False,
            }
            payload["coverage"].append(row)
            try:
                # job ID 来自指定 attempt 列表，下载器另核对所属 run，防止跨运行取日志。
                if job["status"] != "completed":
                    raise DomainError(409, "github_logs_not_ready", "job 尚未结束，日志不完整")
                raw = client.raw_job_log(full_name, target, job["id"])
                add(
                    "log",
                    f"actions/{target}/attempt-{attempt}/job-{job['id']}.log",
                    f"{resource['head_sha']}:attempt-{attempt}:job-{job['id']}",
                    raw,
                )
                row["log_saved"] = True
            except DomainError as error:
                warn(str(job["id"]), error)
    else:
        raise DomainError(422, "unsupported_task", "GitHub 暂不支持此任务类型")
    payload["coverage_complete"] = (
        not payload["warnings"]
        and not payload.get("files_limited")
        and not payload.get("jobs_limited")
        and all(
            row.get("patch_complete") or row.get("supplemented")
            for row in payload["coverage"]
            if "path" in row
        )
    )
    # 元数据同样保存成制品；权限不足时保留明确的缺口，不捏造日志或代码。
    meta = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode()
    add("document", f"github/{kind}-{target}.json", json_digest(payload), meta)
    return captured


def bind_capture(session, run, captured: Captured, store: ArtifactStore):
    # 调用方已经锁定并校验租约；快照、证据绑定与阶段事件在同一提交中完成。
    digest = json_digest(captured.payload)
    snapshot = session.scalar(
        select(ResourceSnapshot).where(
            ResourceSnapshot.repo_id == run.repo_id,
            ResourceSnapshot.kind == captured.kind,
            ResourceSnapshot.external_id == captured.external_id,
            ResourceSnapshot.content_sha256 == digest,
        )
    )
    if snapshot is None:
        session.execute(
            update(ResourceSnapshot)
            .where(
                ResourceSnapshot.repo_id == run.repo_id,
                ResourceSnapshot.kind == captured.kind,
                ResourceSnapshot.external_id == captured.external_id,
                ResourceSnapshot.is_current.is_(True),
            )
            .values(is_current=False)
        )
        snapshot = ResourceSnapshot(
            repo_id=run.repo_id,
            kind=captured.kind,
            external_id=captured.external_id,
            content_sha256=digest,
            payload=captured.payload,
        )
        session.add(snapshot)
        session.flush()
    seen = set()
    for source_type, path, version, raw in captured.sources:
        identity = (source_type, path, version)
        if identity in seen:
            continue
        seen.add(identity)
        key, content_hash, size = store.put_bytes(raw)
        artifact = session.scalar(
            select(ArtifactRecord).where(
                ArtifactRecord.repo_id == run.repo_id, ArtifactRecord.sha256 == content_hash
            )
        )
        if artifact is None:
            artifact = ArtifactRecord(
                repo_id=run.repo_id,
                sha256=content_hash,
                size_bytes=size,
                media_type="text/plain; charset=utf-8",
                storage_key=key,
            )
            session.add(artifact)
            session.flush()
        evidence = session.scalar(
            select(EvidenceRecord).where(
                EvidenceRecord.resource_snapshot_id == snapshot.id,
                EvidenceRecord.source_type == source_type,
                EvidenceRecord.path == path,
                EvidenceRecord.version == version,
            )
        )
        if evidence is None:
            evidence = EvidenceRecord(
                repo_id=run.repo_id,
                resource_snapshot_id=snapshot.id,
                artifact_id=artifact.id,
                source_type=source_type,
                path=path,
                version=version,
                start_line=1,
                end_line=max(
                    1,
                    len(
                        raw.decode("utf-8", errors="replace")
                        .replace("\r\n", "\n")
                        .replace("\r", "\n")
                        .removesuffix("\n")
                        .split("\n")
                    ),
                ),
                retrieved_at=datetime.fromisoformat(captured.payload["captured_at"]),
            )
            session.add(evidence)
            session.flush()
        if session.get(RunEvidenceRecord, (run.id, evidence.id)) is None:
            session.add(
                RunEvidenceRecord(run_id=run.id, evidence_id=evidence.id, repo_id=run.repo_id)
            )
    run.input_version = {
        **run.input_version,
        "resources": [
            {
                **run.input_version["resources"][0],
                "snapshot_id": str(snapshot.id),
                "content_sha256": digest,
                "pending_evidence": False,
                "coverage_complete": captured.payload["coverage_complete"],
                "warnings": captured.payload["warnings"],
            }
        ],
    }
