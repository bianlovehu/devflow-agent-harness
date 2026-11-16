# 文件用途：新增固定提交代码清单，允许独立代码资源证据。
"""code snapshots"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010_code_snapshots"
down_revision = "0009_semantic_memory"
branch_labels = depends_on = None


def upgrade():
    # 原始迁移未命名此约束，按 PostgreSQL 默认名称处理。
    op.drop_constraint("repository_resources_kind_check", "repository_resources", type_="check")
    op.create_check_constraint(
        "repository_resources_kind_check",
        "repository_resources",
        "kind IN ('pull_request','ci_run','document','code_snapshot')",
    )
    op.create_table(
        "code_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("repo_id", sa.String(80), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("coverage", JSONB(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("repo_id", "commit_sha", "policy_version"),
        sa.UniqueConstraint("id", "repo_id"),
        sa.CheckConstraint("status IN ('queued','preparing','ready','partial','failed')"),
    )
    op.create_index("ix_code_snapshots_repo_id", "code_snapshots", ["repo_id"])
    op.create_table(
        "code_files",
        sa.Column("snapshot_id", sa.Uuid(), primary_key=True),
        sa.Column("path", sa.Text(), primary_key=True),
        sa.Column("repo_id", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("blob_sha", sa.String(40)),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Uuid()),
        sa.Column("skip_reason", sa.String(80)),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "repo_id"], ["code_snapshots.id", "code_snapshots.repo_id"]
        ),
        sa.ForeignKeyConstraint(["artifact_id", "repo_id"], ["artifacts.id", "artifacts.repo_id"]),
    )


def downgrade():
    op.drop_table("code_files")
    op.drop_table("code_snapshots")
    op.execute(
        "DELETE FROM run_evidence WHERE evidence_id IN "
        "(SELECT e.id FROM evidence e JOIN repository_resources r "
        "ON e.resource_snapshot_id=r.id WHERE r.kind='code_snapshot')"
    )
    op.execute(
        "DELETE FROM evidence WHERE resource_snapshot_id IN "
        "(SELECT id FROM repository_resources WHERE kind='code_snapshot')"
    )
    op.execute("DELETE FROM repository_resources WHERE kind='code_snapshot'")
    op.drop_constraint("repository_resources_kind_check", "repository_resources", type_="check")
    op.create_check_constraint(
        "repository_resources_kind_check",
        "repository_resources",
        "kind IN ('pull_request','ci_run','document')",
    )
