# 文件用途：定义业务数据库表、唯一约束与跨仓库关联约束。
"""Persistent business facts, immutable evidence and fenced worker leases."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from devflow.database import Base


class RepositoryRecord(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("data_source", "full_name"),
        CheckConstraint("data_source IN ('fixture', 'github')"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    data_source: Mapped[str] = mapped_column(String(16))
    full_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(80))
    default_branch: Mapped[str] = mapped_column(String(255))
    default_commit: Mapped[str] = mapped_column(String(40))
    sync_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResourceSnapshot(Base):
    __tablename__ = "repository_resources"
    __table_args__ = (
        UniqueConstraint("repo_id", "kind", "external_id", "content_sha256"),
        UniqueConstraint("id", "repo_id"),
        CheckConstraint("kind IN ('pull_request', 'ci_run', 'document')"),
        Index(
            "uq_current_repository_resource",
            "repo_id",
            "kind",
            "external_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    external_id: Mapped[str] = mapped_column(String(120))
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationRecord(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("id", "repo_id"),
        CheckConstraint("next_message_sequence > 0"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    next_message_sequence: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageRecord(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence"),
        UniqueConstraint("id", "conversation_id"),
        CheckConstraint("sequence > 0"),
        CheckConstraint("role IN ('user', 'assistant', 'system')"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunRecord(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("id", "repo_id"),
        UniqueConstraint("idempotency_key"),
        Index("ix_runs_worker_queue", "status", "created_at"),
        ForeignKeyConstraint(
            ["conversation_id", "repo_id"], ["conversations.id", "conversations.repo_id"]
        ),
        ForeignKeyConstraint(
            ["message_id", "conversation_id"], ["messages.id", "messages.conversation_id"]
        ),
        CheckConstraint("task_type IN ('pr_review', 'ci_debug', 'knowledge_qa')"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'needs_attention')"
        ),
        CheckConstraint("next_event_sequence > 0"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    task_type: Mapped[str] = mapped_column(String(24))
    target_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    # 任务创建时固定版本和无密钥配置，历史记录不随同步结果改变。
    input_version: Mapped[dict] = mapped_column(JSONB)
    configuration: Mapped[dict] = mapped_column(JSONB)
    configuration_version: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_sha256: Mapped[str] = mapped_column(String(64))
    next_event_sequence: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    # 租约令牌每次领取重新生成；旧进程不能续租或提交已失去所有权的任务。
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retry_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id"))
    result: Mapped[dict | None] = mapped_column(JSONB)
    recovery_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunEventRecord(Base):
    __tablename__ = "run_events"
    __table_args__ = (CheckConstraint("sequence > 0"),)

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("repo_id", "sha256"),
        UniqueConstraint("id", "repo_id"),
        CheckConstraint("size_bytes >= 0"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(120))
    storage_key: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceRecord(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint(
            "resource_snapshot_id", "source_type", "path", "version", "start_line", "end_line"
        ),
        UniqueConstraint("id", "repo_id"),
        ForeignKeyConstraint(
            ["resource_snapshot_id", "repo_id"],
            ["repository_resources.id", "repository_resources.repo_id"],
        ),
        ForeignKeyConstraint(["artifact_id", "repo_id"], ["artifacts.id", "artifacts.repo_id"]),
        CheckConstraint("source_type IN ('file', 'diff', 'log', 'document')"),
        CheckConstraint("start_line > 0 AND end_line >= start_line"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    resource_snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_type: Mapped[str] = mapped_column(String(24))
    path: Mapped[str] = mapped_column(String(512))
    version: Mapped[str] = mapped_column(String(128))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# 两组复合外键同时校验 repo_id，数据库层也禁止把其他仓库的证据绑进任务。
class RunEvidenceRecord(Base):
    __tablename__ = "run_evidence"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "repo_id"], ["runs.id", "runs.repo_id"]),
        ForeignKeyConstraint(["evidence_id", "repo_id"], ["evidence.id", "evidence.repo_id"]),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    repo_id: Mapped[str] = mapped_column(String(80))


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("repo_id", "filename"), UniqueConstraint("id", "repo_id"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(24))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "repo_id"], ["knowledge_documents.id", "knowledge_documents.repo_id"]
        ),
        UniqueConstraint("document_id", "number"),
        UniqueConstraint("id", "repo_id"),
        Index(
            "uq_knowledge_current", "document_id", unique=True, postgresql_where=text("is_current")
        ),
        CheckConstraint("status IN ('indexing', 'ready', 'failed')"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    repo_id: Mapped[str] = mapped_column(String(80), index=True)
    number: Mapped[int] = mapped_column(Integer)
    raw_sha256: Mapped[str] = mapped_column(String(64))
    raw_storage_key: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[str | None] = mapped_column(Text)
    page_starts: Mapped[list] = mapped_column(JSONB, default=list)
    model_key: Mapped[str | None] = mapped_column(String(200))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "repo_id"], ["knowledge_versions.id", "knowledge_versions.repo_id"]
        ),
        Index("ix_knowledge_keywords", "keywords", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    repo_id: Mapped[str] = mapped_column(String(80), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list] = mapped_column(Vector(384))
    keywords: Mapped[str] = mapped_column(TSVECTOR)


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"

    model_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    embedding: Mapped[list] = mapped_column(Vector(384))


class RunJournal(Base):
    __tablename__ = "run_journal"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)


class MemoryRecord(Base):
    __tablename__ = "memories"
    __table_args__ = (
        ForeignKeyConstraint(["source_run_id", "repo_id"], ["runs.id", "runs.repo_id"]),
        UniqueConstraint("source_run_id", "selection"),
        CheckConstraint("status IN ('pending', 'approved', 'revoked', 'superseded')"),
        CheckConstraint("expires_at > created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    source_run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    selection: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB)
    applicable_version: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("memories.id"))
    extraction: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
