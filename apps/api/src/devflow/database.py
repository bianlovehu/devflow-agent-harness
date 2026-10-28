# 文件用途：创建数据库连接池，并为每个请求提供独立会话。
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from devflow.config import Settings


class Base(DeclarativeBase):
    """Shared SQLAlchemy metadata for business tables."""


def create_database_engine(settings: Settings) -> Engine:
    # 集中设置连接池及超时，使数据库故障不会无限阻塞请求。
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )


def get_session(request: Request) -> Iterator[Session]:
    # 请求结束即关闭数据库会话，避免在请求之间共享事务。
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session
