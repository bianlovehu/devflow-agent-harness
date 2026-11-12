# 文件用途：提供记忆提取、审核、编辑、撤销和版本隔离的本地接口。
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator
from sqlalchemy import select

from devflow.budget import BudgetLedger, get_budget_ledger
from devflow.contracts import Contract
from devflow.memory import change_memory, extract_memory
from devflow.models import MemoryRecord
from devflow.workflow_api import Configuration, Database, Page, page
from devflow.workflow_contracts import RecordResponse
from devflow.workflows import require_repository

router = APIRouter(prefix="/api/v1", tags=["memory"])


class MemoryOutput(RecordResponse):
    id: UUID
    repo_id: str
    source_run_id: UUID
    selection: str
    summary: str
    sources: list[dict]
    applicable_version: str | None
    status: Literal["pending", "approved", "revoked", "superseded"]
    expires_at: datetime
    approved_at: datetime | None
    replaces_id: UUID | None
    extraction: dict
    created_at: datetime
    expired: bool = False

    @classmethod
    def from_record(cls, record):
        return cls.model_validate(record).model_copy(
            update={"expired": record.expires_at <= datetime.now(UTC)}
        )


class MemoryExtract(Contract):
    finding_index: int | None = Field(default=None, ge=0, le=19)


class MemoryEdit(Contract):
    summary: str = Field(min_length=1, max_length=2000)
    applicable_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    expires_at: datetime | None = None

    @field_validator("summary")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("经验不能为空")
        return value.strip()

    @field_validator("expires_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("有效期必须包含时区")
        return value


class MemoryApprove(Contract):
    replaces_id: UUID | None = None


@router.post("/runs/{run_id}/memories", response_model=MemoryOutput, status_code=201)
def extract(
    run_id: UUID,
    data: MemoryExtract,
    session: Database,
    settings: Configuration,
    ledger: Annotated[BudgetLedger, Depends(get_budget_ledger)],
):
    return MemoryOutput.from_record(
        extract_memory(session, run_id, data.finding_index, settings, ledger=ledger)
    )


@router.get("/memories", response_model=Page[MemoryOutput])
def memories(
    repo_id: str,
    session: Database,
    settings: Configuration,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_repository(session, repo_id, settings.data_source)
    result = page(
        session,
        select(MemoryRecord)
        .where(MemoryRecord.repo_id == repo_id)
        .order_by(MemoryRecord.created_at.desc(), MemoryRecord.id),
        limit,
        offset,
    )
    result["items"] = [MemoryOutput.from_record(m) for m in result["items"]]
    return result


@router.post("/memories/{memory_id}/edit", response_model=MemoryOutput)
def edit(
    memory_id: UUID, repo_id: str, data: MemoryEdit, session: Database, settings: Configuration
):
    return MemoryOutput.from_record(
        change_memory(session, memory_id, repo_id, "edit", data, settings)
    )


@router.post("/memories/{memory_id}/approve", response_model=MemoryOutput)
def approve(
    memory_id: UUID, repo_id: str, data: MemoryApprove, session: Database, settings: Configuration
):
    return MemoryOutput.from_record(
        change_memory(session, memory_id, repo_id, "approve", data, settings)
    )


@router.post("/memories/{memory_id}/revoke", response_model=MemoryOutput)
def revoke(memory_id: UUID, repo_id: str, session: Database, settings: Configuration):
    return MemoryOutput.from_record(
        change_memory(session, memory_id, repo_id, "revoke", None, settings)
    )
