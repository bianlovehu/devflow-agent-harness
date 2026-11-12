# 文件用途：在隔离数据库验证按会话读取完整历史、稳定分页和仓库隔离。
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import test_persistence_integration as persistence
from devflow.models import RepositoryRecord, RunRecord
from sqlalchemy.orm import Session
from test_persistence_integration import create_target

context = persistence.context
pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1", reason="isolated PostgreSQL required"
)


def submit(context, body):
    result = context.client.post("/api/v1/runs", json=body)
    assert result.status_code == 201, result.text
    return result.json()["id"]


def history(context, conversation_id, **params):
    return context.client.get(
        "/api/v1/runs",
        params={"repo_id": "repo-taskboard", "conversation_id": conversation_id, **params},
    )


def test_conversation_history_paginates_beyond_fifty_without_other_conversations(context):
    first = create_target(context)
    first_ids = [submit(context, first) for _ in range(53)]
    second = create_target(context)
    second_ids = [submit(context, second) for _ in range(2)]
    # 模拟同一时间创建的任务，仍须以 UUID 倒序保证分页顺序稳定。
    same_time = datetime.now(UTC) + timedelta(days=1)
    with Session(context.engine) as session, session.begin():
        # 请求顺序不保证服务器墙钟严格递增；固定数据同时验证倒序及UUID并列排序。
        first_time = same_time - timedelta(days=1)
        for index, run_id in enumerate(first_ids):
            session.get(RunRecord, UUID(run_id)).created_at = first_time + timedelta(
                microseconds=index
            )
        for run_id in second_ids:
            session.get(RunRecord, UUID(run_id)).created_at = same_time
    legacy = context.client.get("/api/v1/runs", params={"repo_id": "repo-taskboard"}).json()
    assert len(legacy["items"]) == 50
    assert all(run["conversation_id"] == first["conversation_id"] for run in legacy["items"])
    selected = history(context, second["conversation_id"])
    assert selected.status_code == 200, selected.text
    assert [run["id"] for run in selected.json()["items"]] == sorted(second_ids, reverse=True)
    page_one = history(context, first["conversation_id"]).json()
    assert len(page_one["items"]) == 50 and page_one["next_offset"] == 50
    page_two = history(context, first["conversation_id"], offset=50).json()
    assert len(page_two["items"]) == 3 and page_two["next_offset"] is None
    rows = page_one["items"] + page_two["items"]
    assert [run["id"] for run in rows] == list(reversed(first_ids))
    assert all(run["conversation_id"] == first["conversation_id"] for run in rows)
    assert len({run["id"] for run in rows}) == 53


def test_history_rejects_invalid_missing_and_cross_repository_conversations(context):
    assert history(context, "invalid").status_code == 422
    missing = history(context, str(uuid4()))
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "conversation_not_found"
    with Session(context.engine) as session, session.begin():
        original = session.get(RepositoryRecord, "repo-taskboard")
        session.add(
            RepositoryRecord(
                id="other-repo",
                data_source="fixture",
                full_name="demo/other",
                description="隔离验证",
                language=original.language,
                default_branch=original.default_branch,
                default_commit=original.default_commit,
                source_updated_at=original.source_updated_at,
            )
        )
    conversation = context.client.post(
        "/api/v1/conversations", json={"repo_id": "other-repo", "title": "其它仓库"}
    )
    assert conversation.status_code == 201
    denied = history(context, conversation.json()["id"])
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "repository_mismatch"


def test_empty_conversation_has_an_explicit_empty_history_page(context):
    body = create_target(context)
    response = history(context, body["conversation_id"])
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_offset": None}
