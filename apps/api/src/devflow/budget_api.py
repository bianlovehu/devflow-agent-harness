# 文件用途：提供只读项目预算与按运行关联的分析/记忆提取费用明细。
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from devflow.budget import BudgetLedger, get_budget_ledger
from devflow.contracts import Contract
from devflow.workflow_api import Database
from devflow.workflows import require_run

router = APIRouter(prefix="/api/v1", tags=["budget"])
Ledger = Annotated[BudgetLedger, Depends(get_budget_ledger)]


class CostResponse(Contract):
    tracked: bool
    settled_cny: str
    reserved_cny: str
    unknown_requests: int
    requests: list[dict]


class BudgetResponse(Contract):
    tracked: bool
    settled_cny: str
    reserved_cny: str
    unknown_requests: int
    total_cny: str
    warning_cny: str
    stop_cny: str
    available_cny: str
    currency: Literal["CNY"]
    status: Literal["ok", "warning", "blocked"]
    limits: dict[str, int]
    basis: str


@router.get("/budget", response_model=BudgetResponse)
def summary(ledger: Ledger):
    return ledger.summary()


@router.get("/runs/{run_id}/cost", response_model=CostResponse)
def run_cost(run_id: UUID, session: Database, ledger: Ledger):
    run = require_run(session, run_id)
    return ledger.snapshot(
        run_id=run_id, tracked=bool(run.configuration.get("runtime_policy_version"))
    )
