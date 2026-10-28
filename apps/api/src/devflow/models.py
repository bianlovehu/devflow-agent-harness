# 文件用途：定义业务数据库表、唯一约束与跨仓库关联约束。
"""Persistent business facts; graph checkpoints and workers arrive later."""

import uuid
from datetime import datetime

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
from sqlalchemy.dialects.postgresql import JSONB
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
