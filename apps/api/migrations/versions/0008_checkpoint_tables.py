# 文件用途：在显式Alembic升级时初始化固定依赖版本的checkpoint表，worker不再执行DDL。
"""Move checkpoint schema setup into the migration entrypoint.

Revision ID: 0008_checkpoint_tables
Revises: 0007_runtime_budget
"""

from alembic import op
from sqlalchemy import text

revision = "0008_checkpoint_tables"
down_revision = "0007_runtime_budget"
branch_labels = None
depends_on = None

# 固定为锁文件中langgraph-checkpoint-postgres的0—9号迁移。
# 此处在Alembic事务内建立普通索引，避免运行期setup及并发DDL。
MIGRATIONS = (
    "CREATE TABLE IF NOT EXISTS checkpoint_migrations (v INTEGER PRIMARY KEY)",
    """CREATE TABLE IF NOT EXISTS checkpoints (
        thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL, parent_checkpoint_id TEXT, type TEXT,
        checkpoint JSONB NOT NULL, metadata JSONB NOT NULL DEFAULT '{}',
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))""",
    """CREATE TABLE IF NOT EXISTS checkpoint_blobs (
        thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
        channel TEXT NOT NULL, version TEXT NOT NULL, type TEXT, blob BYTEA,
        PRIMARY KEY (thread_id, checkpoint_ns, channel, version))""",
    """CREATE TABLE IF NOT EXISTS checkpoint_writes (
        thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL, task_id TEXT NOT NULL, idx INTEGER NOT NULL,
        channel TEXT NOT NULL, type TEXT, blob BYTEA NOT NULL,
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx))""",
    "ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP NOT NULL",
    "SELECT 1",
    "CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id)",
    "CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)",
    "CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)",
    "ALTER TABLE checkpoint_writes ADD COLUMN IF NOT EXISTS task_path TEXT NOT NULL DEFAULT ''",
)


def upgrade():
    connection = op.get_bind()
    connection.execute(text("SET LOCAL search_path = devflow_checkpoints, public"))
    connection.execute(text(MIGRATIONS[0]))
    version = connection.execute(text("SELECT max(v) FROM checkpoint_migrations")).scalar()
    for index, statement in enumerate(MIGRATIONS):
        if version is None or index > version:
            connection.execute(text(statement))
            connection.execute(
                text("INSERT INTO checkpoint_migrations (v) VALUES (:v)"), {"v": index}
            )
    connection.execute(text("SET LOCAL search_path = public"))


def downgrade():
    # 旧版本worker仍兼容这些表；降级保留恢复记录，schema生命周期由0006管理。
    pass
