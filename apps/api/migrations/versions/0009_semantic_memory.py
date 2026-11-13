# 文件用途：添加可失效的记忆向量、内容版本和冲突审核记录；保留既有人工批准状态。
"""semantic memory index

Revision ID: 0009_semantic_memory
Revises: 0008_checkpoint_tables
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_semantic_memory"
down_revision = "0008_checkpoint_tables"
branch_labels = depends_on = None


def upgrade():
    for column in [
        sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("conditions", sa.Text(), nullable=False, server_default=""),
        sa.Column("index_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("index_error", sa.String(80)),
        sa.Column("embedding", Vector(384)),
        sa.Column("embedding_model", sa.Text()),
        sa.Column("embedding_revision", sa.Integer()),
        sa.Column("embedding_sha256", sa.String(64)),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("conflict_reviews", JSONB(), nullable=False, server_default="{}"),
    ]:
        op.add_column("memories", column)


def downgrade():
    for name in [
        "conflict_reviews",
        "indexed_at",
        "embedding_sha256",
        "embedding_revision",
        "embedding_model",
        "embedding",
        "index_error",
        "index_status",
        "conditions",
        "content_revision",
    ]:
        op.drop_column("memories", name)
