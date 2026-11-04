# 文件用途：增加持久化任务租约、取消、执行时间和模拟结果字段。
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_worker_leases"
down_revision: str | None = "0003_github_sync_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("lease_token", "retry_of"):
        op.add_column("runs", sa.Column(name, sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_run_retry_of", "runs", "runs", ["retry_of"], ["id"])
    op.add_column("runs", sa.Column("lease_owner", sa.String(120), nullable=True))
    for name in (
        "lease_expires_at",
        "heartbeat_at",
        "started_at",
        "finished_at",
        "cancel_requested_at",
    ):
        op.add_column("runs", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("attempt", sa.Integer(), server_default="0", nullable=False))
    op.add_column("runs", sa.Column("result", postgresql.JSONB(), nullable=True))
    op.create_index("ix_runs_worker_queue", "runs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_worker_queue", table_name="runs")
    op.drop_constraint("fk_run_retry_of", "runs", type_="foreignkey")
    for name in (
        "lease_token",
        "retry_of",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "started_at",
        "finished_at",
        "cancel_requested_at",
        "attempt",
        "result",
    ):
        op.drop_column("runs", name)
