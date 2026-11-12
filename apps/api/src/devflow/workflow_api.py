# 文件用途：提供会话、任务、事件和制品的 HTTP 接口。
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from devflow.artifact_store import ArtifactStore, get_artifact_store
from devflow.config import Settings, get_settings
from devflow.contracts import Contract
from devflow.database import get_session
from devflow.errors import DomainError
from devflow.event_stream import stream_events
from devflow.models import (
    ArtifactRecord,
    ConversationRecord,
    MessageRecord,
    RunEventRecord,
    RunJournal,
    RunRecord,
)
from devflow.report_v2 import PublicReport
from devflow.reports import report_markdown, require_report
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
    cancel_run,
    create_conversation,
    create_message,
    create_run,
    require_conversation,
    require_repository,
    require_run,
    retry_run,
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


class ReportResponse(Contract):
    report: PublicReport
    markdown: str


class ContextResponse(Contract):
    calls: list[dict]
    recovery_count: int


@router.get("/runs/{run_id}/context", response_model=ContextResponse)
def context_history(
    run_id: UUID, session: Database, call: Annotated[int | None, Query(ge=1)] = None
):
    run = require_run(session, run_id)
    runtime = session.get(RunJournal, (run_id, "runtime"))
    calls = runtime.payload.get("trace", {}).get("calls", []) if runtime else []
    if call is not None:
        calls = [item for item in calls if item["call"] == call]
    else:
        calls = [
            {k: v for k, v in item.items() if k not in {"request", "original_request", "response"}}
            for item in calls
        ]
    return {"calls": calls, "recovery_count": run.recovery_count}


class FreshnessResponse(Contract):
    checked: bool
    stale: bool | None
    analyzed_head: str | None
    current_head: str | None
    note: str


@router.get("/runs/{run_id}/freshness", response_model=FreshnessResponse)
def freshness(run_id: UUID, session: Database, settings: Configuration):
    from devflow.data_source import get_data_source
    from devflow.memory import run_version

    run = require_run(session, run_id)
    repo = require_repository(session, run.repo_id, settings.data_source)
    head = run_version(run.input_version)
    if run.task_type != "pr_review":
        return {
            "checked": False,
            "stale": None,
            "analyzed_head": head,
            "current_head": None,
            "note": "此任务没有 PR，无需检查提交变化",
        }
    if repo.data_source == "github":
        from devflow.github_client import GitHubClient, repo_path

        current_head = GitHubClient(settings).get(
            f"{repo_path(repo.full_name)}/pulls/{run.target_id}"
        )["head"]["sha"]
    else:
        current_head = (
            get_data_source(settings, session)
            .get_pull_request(run.repo_id, int(run.target_id))
            .head_sha
        )
    return {
        "checked": True,
        "stale": head != current_head,
        "analyzed_head": head,
        "current_head": current_head,
        "note": "PR 已变化，旧结论仅适用于固定提交"
        if head != current_head
        else "PR 提交与报告一致",
    }


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
    conversation_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_repository(session, repo_id, settings.data_source)
    query = select(RunRecord).where(RunRecord.repo_id == repo_id)
    if conversation_id is not None:
        conversation = require_conversation(session, conversation_id)
        if conversation.repo_id != repo_id:
            raise DomainError(409, "repository_mismatch", "会话不属于指定仓库")
        query = query.where(RunRecord.conversation_id == conversation_id).order_by(
            RunRecord.created_at.desc(), RunRecord.id.desc()
        )
    else:
        # 未筛选的既有仓库任务接口保持原顺序，避免改变其它调用方的分页语义。
        query = query.order_by(RunRecord.created_at, RunRecord.id)
    return page(
        session,
        query,
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


@router.get("/runs/{run_id}/report", response_model=ReportResponse)
def report(run_id: UUID, session: Database):
    run = require_run(session, run_id)
    document = require_report(run)
    return {
        "report": document.model_dump(mode="json"),
        "markdown": report_markdown(document, run.result, str(run.id)),
    }


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


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
def post_cancel(run_id: UUID, session: Database):
    return cancel_run(session, run_id)


@router.post("/runs/{run_id}/retry", response_model=RunResponse, status_code=201)
def post_retry(
    run_id: UUID,
    response: Response,
    session: Database,
    settings: Configuration,
    store: Store,
    idempotency_key: Annotated[
        str, Header(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    ],
):
    record, replayed = retry_run(session, run_id, settings, store, idempotency_key)
    response.status_code = 200 if replayed else 201
    response.headers["Idempotency-Replayed"] = str(replayed).lower()
    return record


@router.get(
    "/runs/{run_id}/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
def run_stream(
    run_id: UUID,
    request: Request,
    session: Database,
    after: Annotated[int, Query(ge=0, le=999999999)] = 0,
    last_event_id: Annotated[str | None, Header(max_length=9)] = None,
):
    require_run(session, run_id)
    if last_event_id is not None:
        if not last_event_id.isascii() or not last_event_id.isdecimal():
            raise DomainError(422, "invalid_event_cursor", "Last-Event-ID 必须是非负整数")
        after = max(after, int(last_event_id))
    engine = session.get_bind()
    session.rollback()
    return StreamingResponse(
        stream_events(request, engine, run_id, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
