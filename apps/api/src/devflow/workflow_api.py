# 文件用途：提供会话、任务、事件和制品的 HTTP 接口。
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from devflow.artifact_store import ArtifactStore, get_artifact_store
from devflow.config import Settings, get_settings
from devflow.contracts import Contract
from devflow.database import get_session
from devflow.errors import DomainError
from devflow.models import (
    ArtifactRecord,
    ConversationRecord,
    MessageRecord,
    RunEventRecord,
    RunRecord,
)
from devflow.workflow_contracts import (
    ArtifactContent,
    ArtifactResponse,
    ConversationCreate,
    ConversationResponse,
    EvidenceResponse,
    MessageCreate,
    MessageResponse,
    RunCreate,
    RunEventResponse,
    RunResponse,
)
from devflow.workflows import (
    create_conversation,
    create_message,
    create_run,
    require_conversation,
    require_repository,
    require_run,
    run_artifacts,
    run_evidence,
)

router = APIRouter(prefix="/api/v1", tags=["workflows"])
Database = Annotated[Session, Depends(get_session)]
Configuration = Annotated[Settings, Depends(get_settings)]
Store = Annotated[ArtifactStore, Depends(get_artifact_store)]
T = TypeVar("T")


class Page(Contract, Generic[T]):
    items: list[T]
    next_offset: int | None = None


class EventPage(Contract):
    items: list[RunEventResponse]
    next_after: int | None = None


def page(session, query, limit, offset):
    records = session.scalars(query.limit(limit + 1).offset(offset)).all()
    return {
        "items": records[:limit],
        "next_offset": offset + limit if len(records) > limit else None,
    }


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
def post_conversation(data: ConversationCreate, session: Database, settings: Configuration):
    return create_conversation(session, data, settings)


@router.get("/conversations", response_model=Page[ConversationResponse])
def conversations(
    repo_id: str,
    session: Database,
    settings: Configuration,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_repository(session, repo_id, settings.data_source)
    return page(
        session,
        select(ConversationRecord)
        .where(ConversationRecord.repo_id == repo_id)
        .order_by(ConversationRecord.created_at, ConversationRecord.id),
        limit,
        offset,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def conversation(conversation_id: UUID, session: Database):
    return require_conversation(session, conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=201
)
def post_message(conversation_id: UUID, data: MessageCreate, session: Database):
    return create_message(session, conversation_id, data)


@router.get("/conversations/{conversation_id}/messages", response_model=Page[MessageResponse])
def messages(
    conversation_id: UUID,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_conversation(session, conversation_id)
    return page(
        session,
        select(MessageRecord)
        .where(MessageRecord.conversation_id == conversation_id)
        .order_by(MessageRecord.sequence),
        limit,
        offset,
    )


@router.post("/runs", response_model=RunResponse, status_code=201)
def post_run(
    data: RunCreate,
    response: Response,
    session: Database,
    settings: Configuration,
    store: Store,
    idempotency_key: Annotated[
        str | None, Header(max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    ] = None,
):
    record, replayed = create_run(session, data, settings, store, idempotency_key)
    response.status_code = 200 if replayed else 201
    response.headers["Idempotency-Replayed"] = str(replayed).lower()
    return record


@router.get("/runs", response_model=Page[RunResponse])
def runs(
    repo_id: str,
    session: Database,
    settings: Configuration,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_repository(session, repo_id, settings.data_source)
    return page(
        session,
        select(RunRecord)
        .where(RunRecord.repo_id == repo_id)
        .order_by(RunRecord.created_at, RunRecord.id),
        limit,
        offset,
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
def run(run_id: UUID, session: Database):
    return require_run(session, run_id)


@router.get("/runs/{run_id}/events", response_model=EventPage)
def events(
    run_id: UUID,
    session: Database,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    require_run(session, run_id)
    records = session.scalars(
        select(RunEventRecord)
        .where(RunEventRecord.run_id == run_id, RunEventRecord.sequence > after)
        .order_by(RunEventRecord.sequence)
        .limit(limit + 1)
    ).all()
    return {
        "items": records[:limit],
        "next_after": records[limit - 1].sequence if len(records) > limit else None,
    }


@router.get("/runs/{run_id}/evidence", response_model=Page[EvidenceResponse])
def evidence(run_id: UUID, session: Database):
    return {"items": run_evidence(session, run_id)}


@router.get("/runs/{run_id}/artifacts", response_model=Page[ArtifactResponse])
def artifacts(run_id: UUID, session: Database):
    return {"items": run_artifacts(session, run_id)}


@router.get("/artifacts/{artifact_id}", response_model=ArtifactContent)
def artifact(artifact_id: UUID, repo_id: str, session: Database, store: Store):
    record = session.scalar(
        select(ArtifactRecord).where(
            ArtifactRecord.id == artifact_id, ArtifactRecord.repo_id == repo_id
        )
    )
    if record is None:
        raise DomainError(404, "artifact_not_found", "仓库中的制品不存在")
    return {
        "artifact": record,
        "content": store.read_text(record.storage_key, record.sha256),
    }
