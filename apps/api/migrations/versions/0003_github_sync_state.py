# 文件用途：为仓库增加 GitHub 摘要同步状态，保留现有样例与历史任务。
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_github_sync_state"
down_revision: str | None = "0002_business_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("sync_state", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("repositories", "sync_state")
