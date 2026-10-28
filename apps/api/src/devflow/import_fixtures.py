# 文件用途：校验并幂等导入样例仓库、资源快照及证据。
"""Explicit, transactional, idempotent import of the synthetic corpus."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from devflow.artifact_store import ArtifactStore
from devflow.config import get_settings
from devflow.contracts import FixtureDataset
from devflow.data_source import fixture_source
from devflow.database import create_database_engine
from devflow.errors import DomainError
from devflow.models import ArtifactRecord, EvidenceRecord, RepositoryRecord, ResourceSnapshot


def json_digest(payload: dict) -> str:
    # 固定 JSON 字段顺序后计算哈希，避免字段排列影响幂等判断。
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_contents(dataset: FixtureDataset) -> None:
    # 导入前核对声明的内容哈希、日志版本和行数，拒绝自相矛盾的样例元数据。
    def digest(content: str) -> str:
        canonical = content.replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(canonical.encode()).hexdigest()

    prs = {(pr.repo_id, pr.number): pr for pr in dataset.pull_requests}
    if len({repo.id for repo in dataset.repositories}) != len(dataset.repositories):
        raise DomainError(422, "fixture_invalid", "样例仓库标识重复")
    for pr in dataset.pull_requests:
        for file in pr.files:
            if digest(file.head_content) != file.content_sha256:
                raise DomainError(422, "fixture_invalid", "样例文件哈希与内容不一致")
    for run in dataset.ci_runs:
        parent = prs.get((run.repo_id, run.pull_request_number))
        if parent is None or parent.head_sha != run.head_sha:
            raise DomainError(422, "fixture_invalid", "样例 CI 与关联 PR 的版本不一致")
        if digest(run.log) != run.log_sha256:
            raise DomainError(422, "fixture_invalid", "样例日志哈希与内容不一致")
    for doc in dataset.documents:
        if digest(doc.content) != doc.version or len(doc.content.splitlines()) != doc.line_count:
            raise DomainError(422, "fixture_invalid", "样例文档版本或行数不一致")


def import_dataset(
    session: Session, dataset: FixtureDataset, store: ArtifactStore | None = None
) -> dict:
    # 同一导入事务负责仓库、快照和证据写入，重复输入不会产生重复记录。
    validate_contents(dataset)
    store = store or ArtifactStore()
    created = dict.fromkeys(["repositories", "resource_snapshots", "artifacts", "evidence"], 0)
    repo_ids = {repo.id for repo in dataset.repositories}
    if any(repo.data_source != "fixture" for repo in dataset.repositories):
        raise DomainError(422, "fixture_invalid", "样例导入只能包含 fixture 仓库")
    resources = [
        *[("pull_request", str(pr.number), pr) for pr in dataset.pull_requests],
        *[("ci_run", str(run.id), run) for run in dataset.ci_runs],
        *[("document", doc.id, doc) for doc in dataset.documents],
    ]
    if any(
        item.repo_id not in repo_ids or item.data_source != "fixture" for _, _, item in resources
    ):
        raise DomainError(422, "fixture_invalid", "样例资源的仓库或数据源不一致")
    identities = [(item.repo_id, kind, key) for kind, key, item in resources]
    if len(identities) != len(set(identities)):
        raise DomainError(422, "fixture_invalid", "样例资源标识重复")

    with session.begin():
        # Serialize fixture imports across processes. The lock is released on
        # commit/rollback, including a failed import.
        session.execute(select(func.pg_advisory_xact_lock(48151623)))
        for repo in dataset.repositories:
            record = session.get(RepositoryRecord, repo.id)
            if record is None:
                record = RepositoryRecord(id=repo.id)
                session.add(record)
                created["repositories"] += 1
            elif record.data_source != "fixture":
                raise DomainError(409, "repository_conflict", "仓库标识已被其他数据源使用")
            for field in (
                "data_source",
                "full_name",
                "description",
                "language",
                "default_branch",
                "default_commit",
            ):
                setattr(record, field, getattr(repo, field))
            record.source_updated_at = repo.updated_at
            record.updated_at = datetime.now(UTC)
        session.flush()

        def add_evidence(snapshot, kind, path, version, content):
            # 先保存按哈希去重的内容，再把证据行范围关联到固定资源快照。
            key, digest, size = store.put_text(content)
            artifact = session.scalar(
                select(ArtifactRecord).where(
                    ArtifactRecord.repo_id == snapshot.repo_id, ArtifactRecord.sha256 == digest
                )
            )
            if artifact is None:
                artifact = ArtifactRecord(
                    repo_id=snapshot.repo_id,
                    sha256=digest,
                    size_bytes=size,
                    media_type="text/plain; charset=utf-8",
                    storage_key=key,
                )
                session.add(artifact)
                session.flush()
                created["artifacts"] += 1
            end_line = max(1, len(content.splitlines()))
            evidence = session.scalar(
                select(EvidenceRecord).where(
                    EvidenceRecord.resource_snapshot_id == snapshot.id,
                    EvidenceRecord.source_type == kind,
                    EvidenceRecord.path == path,
                    EvidenceRecord.version == version,
                    EvidenceRecord.start_line == 1,
                    EvidenceRecord.end_line == end_line,
                )
            )
            if evidence is None:
                session.add(
                    EvidenceRecord(
                        repo_id=snapshot.repo_id,
                        resource_snapshot_id=snapshot.id,
                        artifact_id=artifact.id,
                        source_type=kind,
                        path=path,
                        version=version,
                        start_line=1,
                        end_line=end_line,
                        retrieved_at=dataset.generated_at,
                    )
                )
                session.flush()
                created["evidence"] += 1

        for kind, external_id, resource in resources:
            payload = resource.model_dump(mode="json")
            digest = json_digest(payload)
            snapshot = session.scalar(
                select(ResourceSnapshot).where(
                    ResourceSnapshot.repo_id == resource.repo_id,
                    ResourceSnapshot.kind == kind,
                    ResourceSnapshot.external_id == external_id,
                    ResourceSnapshot.content_sha256 == digest,
                )
            )
            if snapshot is None or not snapshot.is_current:
                # 先移除旧的当前标记，再启用新快照，满足每个资源只有一个当前版本的约束。
                session.execute(
                    update(ResourceSnapshot)
                    .where(
                        ResourceSnapshot.repo_id == resource.repo_id,
                        ResourceSnapshot.kind == kind,
                        ResourceSnapshot.external_id == external_id,
                        ResourceSnapshot.is_current.is_(True),
                    )
                    .values(is_current=False)
                )
                if snapshot is None:
                    snapshot = ResourceSnapshot(
                        repo_id=resource.repo_id,
                        kind=kind,
                        external_id=external_id,
                        content_sha256=digest,
                        payload=payload,
                        is_current=True,
                    )
                    session.add(snapshot)
                    session.flush()
                    created["resource_snapshots"] += 1
                else:
                    snapshot.is_current = True
                    session.flush()
            if kind == "pull_request":
                for file in resource.files:
                    add_evidence(snapshot, "file", file.path, resource.base_sha, file.base_content)
                    add_evidence(snapshot, "file", file.path, resource.head_sha, file.head_content)
                    add_evidence(snapshot, "diff", file.path, resource.head_sha, file.patch)
            elif kind == "ci_run":
                add_evidence(
                    snapshot, "log", f"ci/{resource.id}.txt", resource.head_sha, resource.log
                )
            else:
                add_evidence(
                    snapshot,
                    "document",
                    f"documents/{resource.id}.md",
                    resource.version,
                    resource.content,
                )
    return {
        "data_source": "fixture",
        "dataset_sha256": json_digest(dataset.model_dump(mode="json")),
        "created": created,
    }


def main() -> None:
    engine = create_database_engine(get_settings())
    try:
        with Session(engine, expire_on_commit=False) as session:
            result = import_dataset(session, fixture_source().dataset)
        print(json.dumps(result, ensure_ascii=False))
    except (SQLAlchemyError, DomainError) as exc:
        code = exc.code if isinstance(exc, DomainError) else "database_unavailable"
        print(
            json.dumps({"status": "error", "code": code, "message": "导入失败，请检查数据和迁移"})
        )
        raise SystemExit(1) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
