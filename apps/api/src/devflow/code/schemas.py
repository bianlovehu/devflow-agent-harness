# 文件用途：代码浏览和搜索的公开请求与响应契约。
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SnapshotRequest(BaseModel):
    commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    retry: bool = False


class CodeSnapshotResponse(BaseModel):
    snapshot_id: UUID
    repo_id: str
    commit: str
    policy_version: str
    status: Literal["queued", "preparing", "ready", "partial", "failed"]
    manifest_sha256: str | None
    coverage: dict
    error_code: str | None
    error_message: str | None


class CodeEntry(BaseModel):
    path: str
    kind: str
    blob_sha: str | None = None
    content_sha256: str | None = None
    size_bytes: int = 0
    line_count: int = 0
    skip_reason: str | None = None


class CodeTreeResponse(CodeSnapshotResponse):
    path: str
    items: list[CodeEntry]
    next_offset: int | None


class CodeLine(BaseModel):
    line: int
    text: str


class CodeFileResponse(CodeSnapshotResponse, CodeEntry):
    start_line: int
    end_line: int
    lines: list[CodeLine]
    next_line: int | None
    redaction_note: str


class CodeSearchRequest(BaseModel):
    snapshot_id: UUID
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=20)
    mode: Literal["snippets", "paths"] = "snippets"


class CodeSearchHit(CodeEntry):
    match_line: int
    start_line: int | None = None
    end_line: int | None = None
    lines: list[CodeLine] | None = None


class CodeSearchResponse(CodeSnapshotResponse):
    path: str
    query: str
    mode: Literal["snippets", "paths"]
    items: list[CodeSearchHit]
    truncated: bool
    truncation_reason: str | None
    search_complete: bool
