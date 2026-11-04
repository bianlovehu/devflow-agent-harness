# 文件用途：以独立 PostgreSQL schema 保存 LangGraph checkpoint，并对每次写入校验租约。
from contextlib import contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row


class LeasedPostgresSaver(PostgresSaver):
    def __init__(self, connection, fence):
        super().__init__(connection)
        self.fence = fence

    def put(self, *args, **kwargs):
        with self.fence():
            return super().put(*args, **kwargs)

    def put_writes(self, *args, **kwargs):
        with self.fence():
            return super().put_writes(*args, **kwargs)


@contextmanager
def postgres_checkpointer(engine, fence):
    arguments = engine.url.translate_connect_args(username="user", database="dbname")
    with psycopg.connect(
        **arguments,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
        options="-c search_path=devflow_checkpoints",
    ) as connection:
        saver = LeasedPostgresSaver(connection, fence)
        # 库自身维护 checkpoint 表版本，串行 setup；业务 Alembic 管理 schema 生命周期。
        connection.execute("SELECT pg_advisory_lock(529053172)")
        try:
            saver.setup()
        finally:
            connection.execute("SELECT pg_advisory_unlock(529053172)")
        yield saver
