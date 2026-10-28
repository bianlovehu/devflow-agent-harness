# 文件用途：以事务保存会话、消息、任务和固定版本的证据引用。
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from devflow import __version__
from devflow.artifact_store import ArtifactStore
from devflow.config import Settings
from devflow.errors import DomainError
from devflow.import_fixtures import json_digest
from devflow.models import (
    ArtifactRecord,
    ConversationRecord,
    EvidenceRecord,
    MessageRecord,
    RepositoryRecord,
    ResourceSnapshot,
    RunEventRecord,
    RunEvidenceRecord,
    RunRecord,
)
from devflow.workflow_contracts import ConversationCreate, MessageCreate, RunCreate


def require_repository(session: Session, repo_id: str, source: str) -> RepositoryRecord:
    repo = session.get(RepositoryRecord, repo_id)
    if repo is None or repo.data_source != source:
        raise DomainError(404, "repository_not_found", "仓库未导入或不存在")
    return repo


def require_conversation(session: Session, conversation_id: uuid.UUID) -> ConversationRecord:
    conversation = session.get(ConversationRecord, conversation_id)
    if conversation is None:
        raise DomainError(404, "conversation_not_found", "会话不存在")
    return conversation


def require_run(session: Session, run_id: uuid.UUID) -> RunRecord:
    run = session.get(RunRecord, run_id)
    if run is None:
        raise DomainError(404, "run_not_found", "任务不存在")
    return run


def create_conversation(session: Session, data: ConversationCreate, settings: Settings):
    with session.begin():
        require_repository(session, data.repo_id, settings.data_source)
        record = ConversationRecord(repo_id=data.repo_id, title=data.title)
        session.add(record)
        session.flush()
    return record


def append_message(session: Session, conversation_id: uuid.UUID, content: str) -> MessageRecord:
    # 锁定会话后分配消息序号，避免并发请求使用相同序号。
    conversation = session.scalar(
        select(ConversationRecord).where(ConversationRecord.id == conversation_id).with_for_update()
    )
    if conversation is None:
        raise DomainError(404, "conversation_not_found", "会话不存在")
    message = MessageRecord(
        conversation_id=conversation.id,
        sequence=conversation.next_message_sequence,
        role="user",
        content=content,
    )
    conversation.next_message_sequence += 1
    session.add(message)
    session.flush()
    return message


def create_message(session: Session, conversation_id: uuid.UUID, data: MessageCreate):
    with session.begin():
        record = append_message(session, conversation_id, data.content)
    return record


def append_run_event(session: Session, run_id: uuid.UUID, event_type: str, payload: dict):
    """Caller owns the transaction; the run row serializes event sequence allocation."""
    # 锁定任务行后递增事件序号，保证同一任务内的顺序唯一。
    run = session.scalar(select(RunRecord).where(RunRecord.id == run_id).with_for_update())
    if run is None:
        raise DomainError(404, "run_not_found", "任务不存在")
    event = RunEventRecord(
        run_id=run.id, sequence=run.next_event_sequence, event_type=event_type, payload=payload
    )
    run.next_event_sequence += 1
    run.updated_at = datetime.now(UTC)
    session.add(event)
    session.flush()
    return event


def _existing_request(session, key, digest):
    # 相同幂等键只能重放相同请求，不能用于另一份任务参数。
    if key is None:
        return None
    run = session.scalar(select(RunRecord).where(RunRecord.idempotency_key == key))
    if run is not None and run.request_sha256 != digest:
        raise DomainError(409, "idempotency_conflict", "幂等键已用于不同的任务请求")
    return run


def create_run(
    session: Session,
    data: RunCreate,
    settings: Settings,
    store: ArtifactStore,
    idempotency_key: str | None = None,
) -> tuple[RunRecord, bool]:
    # 把版本校验、消息、任务及初始事件放进同一事务，失败时一起回滚。
    if settings.data_source != "fixture" or settings.fixture_storage != "database":
        raise DomainError(503, "persistent_storage_required", "当前任务入口需要数据库样例模式")
    digest = json_digest(data.model_dump(mode="json"))
    try:
        with session.begin():
            existing = _existing_request(session, idempotency_key, digest)
            if existing is not None:
                return existing, True
            # Fixture imports take the exclusive form of this transaction lock.
            session.execute(select(func.pg_advisory_xact_lock_shared(48151623)))
            repo = require_repository(session, data.repo_id, settings.data_source)
            conversation = session.scalar(
                select(ConversationRecord)
                .where(ConversationRecord.id == data.conversation_id)
                .with_for_update()
            )
            if conversation is None:
                raise DomainError(404, "conversation_not_found", "会话不存在")
            if conversation.repo_id != repo.id:
                raise DomainError(409, "repository_mismatch", "任务与会话必须属于同一仓库")
            existing = _existing_request(session, idempotency_key, digest)
            if existing is not None:
                return existing, True
            query = select(ResourceSnapshot).where(
                ResourceSnapshot.repo_id == repo.id, ResourceSnapshot.is_current.is_(True)
            )
            if data.task_type == "knowledge_qa":
                query = query.where(ResourceSnapshot.kind == "document")
            else:
                kind = "pull_request" if data.task_type == "pr_review" else "ci_run"
                query = query.where(
                    ResourceSnapshot.kind == kind, ResourceSnapshot.external_id == data.target_id
                )
            snapshots = session.scalars(query.order_by(ResourceSnapshot.external_id)).all()
            if not snapshots:
                raise DomainError(404, "target_not_found", "任务目标或资料未导入")
            evidence = session.scalars(
                select(EvidenceRecord)
                .where(
                    EvidenceRecord.resource_snapshot_id.in_([snapshot.id for snapshot in snapshots])
                )
                .order_by(EvidenceRecord.source_type, EvidenceRecord.path, EvidenceRecord.version)
            ).all()
            if not evidence:
                raise DomainError(409, "evidence_missing", "目标尚无可引用的证据")
            # 写入任务前先确认制品存在且内容完整，防止保存不可回查的引用。
            for item in evidence:
                artifact = session.get(ArtifactRecord, item.artifact_id)
                store.read_text(artifact.storage_key, artifact.sha256)
            # 把输入版本复制进任务；后续资源同步只切换当前快照，不修改这里。
            input_version = {
                "data_source": repo.data_source,
                "repository_commit": repo.default_commit,
                "resources": [
                    {
                        "snapshot_id": str(snapshot.id),
                        "kind": snapshot.kind,
                        "external_id": snapshot.external_id,
                        "content_sha256": snapshot.content_sha256,
                        **{
                            key: snapshot.payload[key]
                            for key in ("base_sha", "head_sha", "version")
                            if key in snapshot.payload
                        },
                    }
                    for snapshot in snapshots
                ],
            }
            configuration = {
                "schema_version": 1,
                "application_version": __version__,
                "model": settings.deepseek_model,
                "executor": "not_implemented",
                "prompt_version": "not_configured",
                "budget": data.budget.model_dump(),
            }
            message = append_message(session, conversation.id, data.question)
            record = RunRecord(
                repo_id=repo.id,
                conversation_id=conversation.id,
                message_id=message.id,
                task_type=data.task_type,
                target_id=data.target_id,
                status="queued",
                input_version=input_version,
                configuration=configuration,
                configuration_version=json_digest(configuration),
                idempotency_key=idempotency_key,
                request_sha256=digest,
            )
            session.add(record)
            session.flush()
            # 任务绑定固定证据 ID，而不是在读取结果时重新选择最新材料。
            session.add_all(
                [
                    RunEvidenceRecord(run_id=record.id, evidence_id=item.id, repo_id=repo.id)
                    for item in evidence
                ]
            )
            append_run_event(
                session,
                record.id,
                "run.queued",
                {"status": "queued", "task_type": data.task_type, "execution_available": False},
            )
        return record, False
    except IntegrityError:
        session.rollback()
        # Handles two requests using the same key in different transactions.
        existing = _existing_request(session, idempotency_key, digest)
        if existing is not None:
            return existing, True
        raise DomainError(409, "write_conflict", "数据写入发生冲突，请重新加载后重试") from None


def run_evidence(session: Session, run_id: uuid.UUID):
    # 只查询创建任务时已绑定的证据，不切换到后来同步的新版本。
    require_run(session, run_id)
    return session.scalars(
        select(EvidenceRecord)
        .join(RunEvidenceRecord, RunEvidenceRecord.evidence_id == EvidenceRecord.id)
        .where(RunEvidenceRecord.run_id == run_id)
        .order_by(EvidenceRecord.source_type, EvidenceRecord.path, EvidenceRecord.version)
    ).all()


def run_artifacts(session: Session, run_id: uuid.UUID):
    require_run(session, run_id)
    return session.scalars(
        select(ArtifactRecord)
        .join(EvidenceRecord, EvidenceRecord.artifact_id == ArtifactRecord.id)
        .join(RunEvidenceRecord, RunEvidenceRecord.evidence_id == EvidenceRecord.id)
        .where(RunEvidenceRecord.run_id == run_id)
        .distinct()
        .order_by(ArtifactRecord.sha256)
    ).all()
