# 文件用途：检测 API、数据库、向量扩展和迁移状态。
from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from devflow import __version__
from devflow.config import PROJECT_ROOT


class ComponentHealth(BaseModel):
    status: Literal["ok", "error", "pending", "unknown"]
    message: str
    version: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str = "devflow-api"
    version: str = __version__
    checked_at: datetime
    checks: dict[str, ComponentHealth]


@lru_cache
def migration_head() -> str | None:
    # 使用当前代码中的迁移头，防止缺少业务表时仍误报数据库已就绪。
    return ScriptDirectory.from_config(Config(str(PROJECT_ROOT / "alembic.ini"))).get_current_head()


def inspect_health(engine: Engine) -> HealthResponse:
    # 分别检测依赖状态，使存活与完整就绪状态可以独立判断。
    checks = {
        "api": ComponentHealth(status="ok", message="FastAPI 服务运行中"),
        "database": ComponentHealth(status="unknown", message="尚未检测数据库"),
        "pgvector": ComponentHealth(status="unknown", message="等待数据库连接"),
        "migrations": ComponentHealth(status="unknown", message="等待数据库连接"),
    }
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            postgres_version = connection.execute(text("SHOW server_version")).scalar_one()
            checks["database"] = ComponentHealth(
                status="ok", message="PostgreSQL 已连接", version=postgres_version
            )
            vector_version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
            checks["pgvector"] = ComponentHealth(
                status="ok" if vector_version else "pending",
                message="向量扩展已启用" if vector_version else "请先运行数据库迁移",
                version=vector_version,
            )
            has_migrations = connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar_one_or_none()
            revision = (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                if has_migrations
                else None
            )
            checks["migrations"] = ComponentHealth(
                status="ok" if revision == migration_head() else "pending",
                message="迁移已应用"
                if revision == migration_head()
                else "请运行 uv run alembic upgrade head",
                version=revision,
            )
    except SQLAlchemyError:
        checks["database"] = ComponentHealth(
            status="error", message="数据库检测失败，请检查 Docker、连接配置和迁移"
        )

    return HealthResponse(
        status="ok" if all(check.status == "ok" for check in checks.values()) else "degraded",
        checked_at=datetime.now(UTC),
        checks=checks,
    )
