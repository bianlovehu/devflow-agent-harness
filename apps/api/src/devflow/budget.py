# 文件用途：主数据库中的全项目预算预留、幂等结算及未知用量保留。
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.errors import DomainError
from devflow.models import BudgetAccount, ModelCharge
from devflow.runtime_policy import cost, limits, pricing


class BudgetLedger:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    @contextmanager
    def transaction(self):
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                yield session
        except SQLAlchemyError:
            raise DomainError(503, "budget_unavailable", "预算账本不可用，真实请求已停止") from None

    def account(self, session):
        session.execute(
            insert(BudgetAccount)
            .values(id="project", settled_cny=0, reserved_cny=0)
            .on_conflict_do_nothing()
        )
        return session.scalar(
            select(BudgetAccount).where(BudgetAccount.id == "project").with_for_update()
        )

    def reserve(
        self,
        *,
        provider,
        model,
        base_url,
        estimated_input,
        output_limit,
        purpose,
        run_id=None,
        source="cli",
        timeout=90,
    ):
        quote = pricing(provider, model, base_url)
        amount = cost(estimated_input, output_limit, quote)
        denied = False
        with self.transaction() as session:
            account = self.account(session)
            now = session.scalar(select(func.clock_timestamp()))
            expired = session.scalars(
                select(ModelCharge)
                .where(
                    ModelCharge.status.in_(["reserved", "inflight"]), ModelCharge.expires_at <= now
                )
                .with_for_update()
            ).all()
            for item in expired:
                if item.status == "reserved":
                    account.reserved_cny -= item.reserved_cny
                    item.status = "released"  # 尚未提交 dispatch 标记，确定没有发出请求。
                else:
                    item.status = "uncertain"
            projected = account.settled_cny + account.reserved_cny + amount
            warning = account.warned_at is None and projected >= self.settings.budget_warning_cny
            if projected > self.settings.budget_stop_cny:
                denied = True
                warning = False
            else:
                if warning:
                    account.warned_at = now
                account.reserved_cny += amount
                request_id = uuid.uuid4()
                session.add(
                    ModelCharge(
                        id=request_id,
                        account_id="project",
                        run_id=run_id,
                        purpose=purpose,
                        source=source,
                        status="reserved",
                        estimated_input=estimated_input,
                        output_limit=output_limit,
                        reserved_cny=amount,
                        pricing=quote,
                        expires_at=now + timedelta(seconds=timeout + 10),
                    )
                )
        if denied:
            raise DomainError(
                409,
                "cost_budget_exceeded",
                f"预计费用将超过{self.settings.budget_stop_cny}元停止线，真实请求未发送",
            )
        return {
            "request_id": str(request_id),
            "reserved_cny": str(amount),
            "warning": warning,
            "pricing_version": quote["version"],
            "warning_cny": str(self.settings.budget_warning_cny),
        }

    def dispatch(self, request_id):
        with self.transaction() as session:
            self.account(session)
            record = session.get(ModelCharge, uuid.UUID(str(request_id)), with_for_update=True)
            if record.status != "reserved" or record.expires_at <= datetime.now(UTC):
                raise DomainError(409, "cost_budget_exceeded", "费用预留已失效，请重新发起请求")
            record.status = "inflight"

    def finish(self, request_id, usage=None, *, sent=True):
        warning = False
        with self.transaction() as session:
            account = self.account(session)
            record = session.get(ModelCharge, uuid.UUID(str(request_id)), with_for_update=True)
            if record.status in {"settled", "released"}:
                return
            if not sent:
                record.status = "released"
                account.reserved_cny -= record.reserved_cny
            elif usage is None:
                record.status = "uncertain"
            else:
                amount = cost(usage.prompt_tokens, usage.completion_tokens, record.pricing)
                account.reserved_cny -= record.reserved_cny
                account.settled_cny += amount
                record.status, record.settled_cny = "settled", amount
                record.usage = usage.model_dump()
                if (
                    account.warned_at is None
                    and account.settled_cny + account.reserved_cny
                    >= self.settings.budget_warning_cny
                ):
                    account.warned_at = datetime.now(UTC)
                    warning = True
        return {"warning": warning, "warning_cny": str(self.settings.budget_warning_cny)}

    def snapshot(self, *, run_id=None, tracked=True, include_requests=True):
        with self.transaction() as session:
            account = session.get(BudgetAccount, "project")
            if run_id is None and not include_requests:
                unknown = session.scalar(
                    select(func.count())
                    .select_from(ModelCharge)
                    .where(
                        or_(
                            ModelCharge.status == "uncertain",
                            (ModelCharge.status == "inflight")
                            & (ModelCharge.expires_at <= func.clock_timestamp()),
                        )
                    )
                )
                return {
                    "tracked": True,
                    "settled_cny": str(account.settled_cny if account else 0),
                    "reserved_cny": str(account.reserved_cny if account else 0),
                    "unknown_requests": unknown,
                    "requests": [],
                }
            query = select(ModelCharge)
            if run_id is not None:
                query = query.where(ModelCharge.run_id == run_id)
            rows = session.scalars(query.order_by(ModelCharge.created_at, ModelCharge.id)).all()
            settled = sum((r.settled_cny or Decimal(0) for r in rows), Decimal(0))
            reserved = sum(
                (r.reserved_cny for r in rows if r.status in {"reserved", "inflight", "uncertain"}),
                Decimal(0),
            )
            if run_id is None and account:
                settled, reserved = account.settled_cny, account.reserved_cny
            now = datetime.now(UTC)
            unknown = sum(
                r.status == "uncertain" or (r.status == "inflight" and r.expires_at <= now)
                for r in rows
            )
            return {
                "tracked": tracked or bool(rows),
                "settled_cny": str(settled),
                "reserved_cny": str(reserved),
                "unknown_requests": unknown,
                "requests": [
                    {
                        "request_id": str(r.id),
                        "purpose": r.purpose,
                        "source": r.source,
                        "status": "uncertain"
                        if r.status == "inflight" and r.expires_at <= now
                        else r.status,
                        "estimated_input": r.estimated_input,
                        "output_limit": r.output_limit,
                        "reserved_cny": str(r.reserved_cny),
                        "settled_cny": str(r.settled_cny) if r.settled_cny is not None else None,
                        "pricing": r.pricing,
                        "usage": r.usage,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rows
                ],
            }

    def summary(self):
        value = self.snapshot(include_requests=False)
        total, warning, stop = (
            self.settings.budget_total_cny,
            self.settings.budget_warning_cny,
            self.settings.budget_stop_cny,
        )
        used = Decimal(value["settled_cny"]) + Decimal(value["reserved_cny"])
        value.pop("requests")
        return {
            **value,
            "total_cny": str(total),
            "warning_cny": str(warning),
            "stop_cny": str(stop),
            "available_cny": str(max(Decimal(0), stop - used)),
            "currency": "CNY",
            "status": "blocked" if used >= stop else "warning" if used >= warning else "ok",
            "limits": {
                **limits(),
                "input_tokens": min(self.settings.context_input_tokens, limits()["input_tokens"]),
                "output_tokens": min(
                    self.settings.model_max_output_tokens, limits()["output_tokens"]
                ),
                "model_timeout_seconds": min(
                    self.settings.model_timeout_seconds, limits()["model_timeout_seconds"]
                ),
            },
            "basis": "保守目录价估算，不代表供应商最终账单",
        }


@lru_cache
def get_budget_ledger():
    # 使用进程启动配置中的主库，不跟随 worker/验收脚本传入的临时分析库切换。
    settings = get_settings()
    return BudgetLedger(create_database_engine(settings), settings)
