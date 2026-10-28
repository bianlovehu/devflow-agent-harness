# 文件用途：定义仓库、PR、CI 和文档的接口数据结构。
"""Business read contracts shared by fixture and future GitHub adapters."""

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataSource = Literal["fixture", "github"]
Commit = str
T = TypeVar("T")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Collection(Contract, Generic[T]):
    data_source: DataSource
    items: list[T]


class Repository(Contract):
    id: str
    data_source: DataSource
    full_name: str
    description: str
    language: str
    default_branch: str
    default_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    updated_at: datetime
    pull_request_count: int
    ci_run_count: int
    document_count: int


class PullRequestSummary(Contract):
    repo_id: str
    data_source: DataSource
    number: int
    title: str
    body: str
    author: str
    state: Literal["open", "closed", "merged"]
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    updated_at: datetime


class ChangedFile(Contract):
    path: str
    additions: int
    deletions: int
    patch: str
    base_content: str
    head_content: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PullRequestDetail(PullRequestSummary):
    files: list[ChangedFile]


class CIRunSummary(Contract):
    id: int
    repo_id: str
    data_source: DataSource
    pull_request_number: int
    name: str
    conclusion: Literal["success", "failure", "cancelled"]
    stage: Literal["install", "test", "configure"]
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    started_at: datetime
    duration_seconds: int


class CIRunDetail(CIRunSummary):
    log: str
    log_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DocumentSummary(Contract):
    id: str
    repo_id: str
    data_source: DataSource
    title: str
    kind: Literal["architecture", "policy", "runbook", "postmortem"]
    version: str = Field(pattern=r"^[0-9a-f]{64}$")
    updated_at: datetime
    line_count: int


class DocumentDetail(DocumentSummary):
    content: str


class FixtureDataset(Contract):
    schema_version: Literal[1]
    generated_at: datetime
    repositories: list[Repository]
    pull_requests: list[PullRequestDetail]
    ci_runs: list[CIRunDetail]
    documents: list[DocumentDetail]
