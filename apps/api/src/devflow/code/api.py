# 文件用途：代码工作台接口，只读指定快照，准备请求进入持久化队列。
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from devflow.code import service
from devflow.code.schemas import (
    CodeFileResponse,
    CodeSearchRequest,
    CodeSearchResponse,
    CodeSnapshotResponse,
    CodeSnapshotSelection,
    CodeTreeResponse,
    SnapshotRequest,
)
from devflow.core.config import Settings, get_settings
from devflow.storage.artifact_store import ArtifactStore, get_artifact_store
from devflow.storage.database import get_session

router = APIRouter(prefix="/api/v1/repositories/{repo_id}/code", tags=["code"])
Database = Annotated[Session, Depends(get_session)]
Store = Annotated[ArtifactStore, Depends(get_artifact_store)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/snapshots", response_model=CodeSnapshotResponse)
def prepare(repo_id: str, body: SnapshotRequest, session: Database, response: Response):
    with session.begin():
        row = service.request_snapshot(session, repo_id, body.commit, retry=body.retry)
        result = service.describe(row)
    response.status_code = 200 if row.status in {"ready", "partial"} else 202
    return result


@router.get("/snapshots", response_model=CodeSnapshotSelection)
def cached(
    repo_id: str,
    session: Database,
    commit: str | None = Query(default=None, pattern=r"^[0-9a-f]{40}$"),
):
    repo = service.repository(session, repo_id)
    row = service.cached_snapshot(session, repo_id, commit)
    return {
        "repo_id": repo_id,
        "default_commit": repo.default_commit,
        "snapshot": service.describe(row) if row else None,
    }


@router.post("/pull", response_model=CodeSnapshotResponse)
def pull(repo_id: str, session: Database, settings: Config, response: Response):
    with session.begin():
        row = service.pull_latest(session, repo_id, settings)
        result = service.describe(row)
    response.status_code = 200 if row.status in {"ready", "partial"} else 202
    return result


@router.get("/snapshots/{snapshot_id}", response_model=CodeSnapshotResponse)
def status(repo_id: str, snapshot_id: UUID, session: Database):
    return service.describe(service.snapshot(session, repo_id, snapshot_id, ready=False))


@router.get("/tree", response_model=CodeTreeResponse)
def tree(
    repo_id: str,
    snapshot_id: UUID,
    session: Database,
    path: str = "",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
):
    return service.tree(session, repo_id, snapshot_id, path, offset, limit)


@router.get("/file", response_model=CodeFileResponse)
def file(
    repo_id: str,
    snapshot_id: UUID,
    path: str,
    session: Database,
    store: Store,
    start_line: int = Query(default=1, ge=1),
    limit: int = Query(default=60, ge=1, le=100),
):
    return service.read_file(session, repo_id, snapshot_id, path, start_line, limit, store)


@router.post("/search", response_model=CodeSearchResponse)
def search(
    repo_id: str, body: CodeSearchRequest, session: Database, store: Store, settings: Config
):
    return service.search(
        session, repo_id, body.snapshot_id, body.query, body.limit, body.mode, store, settings
    )
