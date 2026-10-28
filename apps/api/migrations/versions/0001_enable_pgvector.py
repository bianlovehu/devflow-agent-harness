# 文件用途：通过初始迁移启用 PostgreSQL 向量扩展。
"""Enable the pgvector extension.

Revision ID: 0001_enable_pgvector
Revises: None
"""

from alembic import op

revision = "0001_enable_pgvector"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # The extension may be shared with other applications. Keep it on rollback.
    pass
