# 文件用途：定义会话、消息、任务及证据接口的输入输出结构。
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from devflow.contracts import Contract

NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
]
RepoId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]+$", max_length=80)]
TaskType = Literal["pr_review", "ci_debug", "knowledge_qa"]
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "needs_attention"]
RunFailureCode = Literal[
    "model_error",
    "tool_error",
    "budget_exceeded",
    "timeout",
    "input_changed",
    "artifact_missing",
    "worker_lost",
    "internal_error",
]


class RecordResponse(Contract):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ConversationCreate(Contract):
    repo_id: RepoId
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ConversationResponse(RecordResponse):
    id: UUID
    repo_id: str
    title: str
    created_at: datetime


class MessageCreate(Contract):
    content: NonEmptyText


class MessageResponse(RecordResponse):
    id: UUID
    conversation_id: UUID
    sequence: int
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class RunBudget(Contract):
    max_model_calls: int = Field(default=6, ge=1, le=20)
    max_tool_calls: int = Field(default=12, ge=1, le=60)
    max_total_tokens: int = Field(default=60000, ge=1000, le=1000000)
    timeout_seconds: int = Field(default=600, ge=10, le=1800)


class RunCreate(Contract):
    repo_id: RepoId
    conversation_id: UUID
    task_type: TaskType
    target_id: str | None = Field(default=None, max_length=120)
    question: NonEmptyText
    budget: RunBudget = Field(default_factory=RunBudget)

    @model_validator(mode="after")
    def target_matches_task(self):
        if self.task_type == "knowledge_qa":
            if self.target_id is not None:
                raise ValueError("knowledge_qa 不指定 target_id")
        elif (
            self.target_id is None or not self.target_id.isascii() or not self.target_id.isdecimal()
        ):
            raise ValueError("PR 或 CI 任务需要数字形式的 target_id")
        elif int(self.target_id) <= 0:
            raise ValueError("target_id 必须为正数")
        else:
            self.target_id = str(int(self.target_id))
        return self


class RunResponse(RecordResponse):
    id: UUID
    repo_id: str
    conversation_id: UUID
    message_id: UUID
    task_type: TaskType
    target_id: str | None
    status: RunStatus
    input_version: dict
    configuration: dict
    configuration_version: str
    error_code: RunFailureCode | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    execution_available: bool = False


class RunEventResponse(RecordResponse):
    run_id: UUID
    sequence: int
    event_type: str
    payload: dict
    created_at: datetime


class ArtifactResponse(RecordResponse):
    id: UUID
    repo_id: str
    sha256: str
    size_bytes: int
    media_type: str
    created_at: datetime


class EvidenceResponse(RecordResponse):
    id: UUID
    repo_id: str
    resource_snapshot_id: UUID
    artifact_id: UUID
    source_type: str
    path: str
    version: str
    start_line: int
    end_line: int
    retrieved_at: datetime


class ArtifactContent(Contract):
    artifact: ArtifactResponse
    content: str
