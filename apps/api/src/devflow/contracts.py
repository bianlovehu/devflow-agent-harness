# 文件用途：定义样例和 GitHub 共用的仓库、资源及来源状态契约。
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataSource = Literal["fixture", "github"]
Commit = str
T = TypeVar("T")


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceNotice(Contract):
    code: str
    message: str
    retry_after: int | None = None


class ModelInfo(Contract):
    provider: str
    name: str
    configured: bool


class RuntimeInfo(Contract):
    data_source: DataSource
    fixture_storage: Literal["database", "files"]
    task_execution_available: bool
    repository_adapter_available: bool
    github_configured: bool = False
    model: ModelInfo


class Collection(Contract, Generic[T]):
    data_source: DataSource
    items: list[T]
    fetched_at: datetime | None = None
    limited: bool = False
    warnings: list[SourceNotice] = Field(default_factory=list)


class RepositoryCreate(Contract):
    url: str = Field(min_length=3, max_length=300)


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
    fetched_at: datetime | None = None
    sync_warnings: list[SourceNotice] = Field(default_factory=list)


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
    fetched_at: datetime | None = None
    html_url: str | None = None


class ChangedFile(Contract):
    path: str
    additions: int
    deletions: int
    patch: str
    base_content: str | None = None
    head_content: str | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: str = "modified"
    previous_path: str | None = None
    patch_available: bool = True


class LinkedIssue(Contract):
    number: int
    title: str
    body: str
    state: str
    html_url: str
    relation: Literal["body_reference"] = "body_reference"


class PullRequestDetail(PullRequestSummary):
    files: list[ChangedFile]
    files_limited: bool = False
    linked_issues: list[LinkedIssue] = Field(default_factory=list)
    warnings: list[SourceNotice] = Field(default_factory=list)


class CIRunSummary(Contract):
    id: int
    repo_id: str
    data_source: DataSource
    pull_request_number: int | None
    name: str
    conclusion: str | None
    stage: Literal["install", "test", "configure"] | None
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    started_at: datetime
    duration_seconds: int | None
    status: str = "completed"
    run_attempt: int = 1
    html_url: str | None = None
    fetched_at: datetime | None = None


class CIStep(Contract):
    number: int
    name: str
    status: str
    conclusion: str | None = None


class CIJob(Contract):
    id: int
    run_id: int
    name: str
    status: str
    conclusion: str | None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[CIStep] = Field(default_factory=list)


class CIRunDetail(CIRunSummary):
    log: str | None = None
    log_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    jobs: list[CIJob] = Field(default_factory=list)
    jobs_limited: bool = False
    warnings: list[SourceNotice] = Field(default_factory=list)


class JobLog(Contract):
    repo_id: str
    run_id: int
    job_id: int
    fetched_at: datetime
    content: str
    content_sha256: str


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
