# 文件用途：在真实pgvector库验证30条以上记忆、索引失效、冲突审核和运行时撤销隔离。
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import test_persistence_integration as persistence
from devflow.embeddings import MODEL_KEY
from devflow.knowledge_api import embedding_factory
from devflow.main import app
from devflow.memory import content_digest, index_memory, recall_memories
from devflow.models import MemoryRecord, RepositoryRecord
from sqlalchemy.orm import Session
from test_week05_integration import candidate, completed, create_agent_run

context = persistence.context
pytestmark = persistence.pytestmark


class TopicEmbedder:
    key = MODEL_KEY

    def encode(self, texts, **kwargs):
        result = []
        for text in texts:
            topic = "owner" if any(w in text for w in ["owner_id", "租户", "所有者"]) else text
            slot = int(hashlib.sha256(topic.encode()).hexdigest()[:8], 16) % 384
            vector = [0.0] * 384
            vector[slot] = 1.0
            result.append(vector)
        return result


def action(context, memory, name, data=None):
    return context.client.post(
        f"/api/v1/memories/{memory['id']}/{name}?repo_id=repo-taskboard", json=data or {}
    )


def index(context, memory):
    app.dependency_overrides[embedding_factory] = lambda: TopicEmbedder
    result = action(context, memory, "index")
    assert result.status_code == 200, result.text
    return result.json()


def search(context, query="不同租户能否看到别人的任务", version=None):
    result = context.client.post(
        "/api/v1/memories/search",
        json={
            "repo_id": "repo-taskboard",
            "query": query,
            "version": version,
        },
    )
    assert result.status_code == 200, result.text
    return result.json()["items"]


def test_thirty_older_semantic_hit_filters_before_ranking_and_source_revoke(context):
    run = completed(context)
    now = datetime.now(UTC)
    vector = TopicEmbedder().encode(["owner_id"])[0]
    with Session(context.engine) as session, session.begin():
        session.add(
            RepositoryRecord(
                id="other",
                full_name="other/other",
                description="隔离验证",
                language="Python",
                default_commit="a" * 40,
                source_updated_at=now,
                default_branch="main",
                data_source="fixture",
            )
        )
        for i in range(37):
            record = MemoryRecord(
                repo_id="repo-taskboard",
                source_run_id=UUID(run["id"]),
                selection=f"seed-{i}",
                summary="owner_id 所有者隔离" if i == 0 or i >= 30 else f"不相关背景主题编号{i}",
                conditions="仅任务列表查询",
                sources=[{"source": "fixture-report"}],
                status="approved",
                applicable_version=None,
                extraction={"provider": "fixture"},
                created_at=now - timedelta(days=40),
                approved_at=now - timedelta(days=30 - i / 10),
                expires_at=now + timedelta(days=10),
                content_revision=1,
            )
            session.add(record)
            session.flush()
            record.embedding = TopicEmbedder().encode([record.summary])[0]
            record.embedding_model, record.embedding_revision = MODEL_KEY, 1
            record.embedding_sha256, record.index_status = content_digest(record), "ready"
            if i == 30:
                record.status = "revoked"
            if i == 31:
                record.expires_at = now - timedelta(days=1)
            if i == 32:
                record.applicable_version = "f" * 40
            if i == 33:
                record.status = "pending"
            if i == 34:
                record.embedding_revision = 0
            if i == 35:
                record.embedding_model = "obsolete-model"
            if i == 36:
                record.embedding_sha256 = "0" * 64
        session.flush()
        # 跨仓库条目通过另一个来源run构建，不能违反来源复合外键。
        from devflow.models import ConversationRecord, MessageRecord, RunRecord

        conversation = ConversationRecord(repo_id="other", title="other")
        session.add(conversation)
        session.flush()
        message = MessageRecord(
            conversation_id=conversation.id, role="user", content="q", sequence=1
        )
        session.add(message)
        session.flush()
        foreign_run = RunRecord(
            repo_id="other",
            conversation_id=conversation.id,
            message_id=message.id,
            task_type="pr_review",
            target_id="1",
            status="succeeded",
            input_version={},
            configuration={},
            configuration_version="a" * 64,
            request_sha256="b" * 64,
        )
        session.add(foreign_run)
        session.flush()
        other = MemoryRecord(
            repo_id="other",
            source_run_id=foreign_run.id,
            selection="answer",
            summary="owner_id 所有者隔离",
            sources=[],
            conditions="",
            status="approved",
            expires_at=now + timedelta(days=1),
            extraction={},
            content_revision=1,
            embedding=vector,
            embedding_model=MODEL_KEY,
            embedding_revision=1,
            index_status="ready",
        )
        session.add(other)
        other.embedding_sha256 = content_digest(other)
    app.dependency_overrides[embedding_factory] = lambda: TopicEmbedder
    found = search(context)
    assert len(found) == 1 and found[0]["summary"] == "owner_id 所有者隔离"
    assert found[0]["match_reason"] and found[0]["conditions"] and found[0]["sources"]
    with Session(context.engine) as session:
        recent = recall_memories(session, "repo-taskboard", None)
        assert found[0]["id"] not in {m["id"] for m in recent}
    assert search(context, "火星地质勘探") == []
    revoked = context.client.post(f"/api/v1/runs/{run['id']}/memories/revoke-source", json={})
    assert revoked.status_code == 200 and len(revoked.json()["revoked_ids"]) == 37
    assert search(context) == []
    with Session(context.engine) as session:
        assert recall_memories(session, "other", None)[0]["summary"] == "owner_id 所有者隔离"


def test_edit_requires_new_index_review_and_stale_conflict_ack_cannot_overwrite(context):
    run = completed(context)
    old = candidate(context, run)
    old = index(context, old)
    assert action(context, old, "approve").status_code == 200
    new = candidate(context, completed(context))
    assert action(context, new, "edit", {"summary": "owner_id 无需隔离所有者"}).status_code == 200
    new = index(context, new)
    assert new["conflicts"] and new["conflicts"][0]["diff"]
    assert action(context, new, "approve").status_code == 409
    expected = {c["id"]: c["content_revision"] for c in new["conflicts"]}
    edited = action(
        context, old, "edit", {"summary": "owner_id 必须隔离所有者", "conditions": "列表API"}
    )
    assert edited.status_code == 200
    assert not edited.json()["index_current"] and edited.json()["content_revision"] == 2
    assert action(context, old, "approve").json()["detail"]["code"] == "memory_index_required"
    assert index(context, old)["index_current"]
    assert action(context, old, "approve").status_code == 200
    assert action(context, new, "approve", {"reviewed_conflicts": expected}).status_code == 409
    new = index(context, new)
    reviewed = {c["id"]: c["content_revision"] for c in new["conflicts"]}
    result = action(
        context, new, "approve", {"reviewed_conflicts": reviewed, "replaces_id": old["id"]}
    )
    assert result.status_code == 200, result.text
    assert result.json()["conflict_reviews"]["conflicts"]
    with Session(context.engine) as session:
        assert session.get(MemoryRecord, UUID(old["id"])).status == "superseded"


def test_index_failure_and_edit_during_inference_do_not_restore_stale_content(context):
    memory = candidate(context, completed(context))

    def fail():
        raise RuntimeError("private details")

    app.dependency_overrides[embedding_factory] = lambda: fail
    result = action(context, memory, "index")
    assert result.status_code == 200 and result.json()["index_status"] == "failed"
    assert "private details" not in result.text
    assert action(context, memory, "approve").status_code == 409

    class RacingEmbedder(TopicEmbedder):
        def encode(self, texts, **kwargs):
            edited = action(context, memory, "edit", {"summary": "并发编辑后的新摘要"})
            assert edited.status_code == 200
            return super().encode(texts, **kwargs)

    with Session(context.engine, expire_on_commit=False) as session:
        from devflow.errors import DomainError

        with pytest.raises(DomainError, match="索引期间经验已变化"):
            index_memory(
                session,
                UUID(memory["id"]),
                "repo-taskboard",
                context.settings,
                embedder_factory=RacingEmbedder,
            )
    indexed = index(context, memory)
    assert indexed["summary"] == "并发编辑后的新摘要" and indexed["embedding_revision"] == 2


def test_semantic_worker_records_explanations_and_rechecks_revocation(context):
    from devflow.fake_model import FixtureModel

    memory = index(context, candidate(context, completed(context)))
    assert action(context, memory, "approve").status_code == 200
    context.settings = context.settings.model_copy(update={"memory_recall_strategy": "semantic"})
    run, worker = create_agent_run(context, question="owner_id 所有者隔离核查")
    worker.embedder_factory = TopicEmbedder

    worker.execute(*worker.claim(UUID(run["id"])))
    saved = context.client.get(f"/api/v1/runs/{run['id']}").json()
    assert saved["status"] == "succeeded"
    detail = saved["result"]["recalled_memory_details"][0]
    assert detail["id"] == memory["id"] and detail["match_reason"] and detail["sources"]
    run, worker = create_agent_run(context, question="owner_id 所有者隔离核查")
    worker.embedder_factory = TopicEmbedder

    class RevokingModel(FixtureModel):
        def __init__(self):
            self.requests = []

        def complete(self, messages, tools, **kwargs):
            self.requests.append(messages)
            if len(self.requests) == 1:
                assert action(context, memory, "revoke").status_code == 200
            return super().complete(messages, tools, **kwargs)

    model = RevokingModel()
    worker.model_factory = lambda _: model
    worker.execute(*worker.claim(UUID(run["id"])))
    import json

    assert memory["id"] in json.dumps(model.requests[0])
    assert memory["id"] not in json.dumps(model.requests[1])
    result = context.client.get(f"/api/v1/runs/{run['id']}").json()
    assert result["status"] == "succeeded" and result["result"]["memory_strategy"] == "semantic"
