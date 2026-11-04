# 文件用途：在隔离 PostgreSQL 中验证知识版本、删除、仓库隔离与 Agent 文档引用。
import base64
import os
from uuid import UUID

import pytest
import test_persistence_integration as persistence
from devflow.embeddings import MODEL_KEY
from devflow.knowledge_api import embedding_factory
from devflow.main import app
from devflow.models import KnowledgeChunk, KnowledgeVersion, RepositoryRecord, RunRecord
from devflow.worker import Worker
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_knowledge import CharacterTokenizer

context = persistence.context
pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1", reason="isolated PostgreSQL required"
)


class TestEmbedder:
    __test__ = False
    key, tokenizer = MODEL_KEY, CharacterTokenizer()

    def encode(self, texts, **kwargs):
        return [[1.0] + [0.0] * 383 for _ in texts]


def upload(
    context, content="任务所有者 owner_id 必须隔离", filename="policy.md", repo="repo-taskboard"
):
    app.dependency_overrides[embedding_factory] = lambda: TestEmbedder
    response = context.client.post(
        "/api/v1/knowledge/upload",
        json={
            "repo_id": repo,
            "filename": filename,
            "content_base64": base64.b64encode(content.encode()).decode(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def search(context, query="所有者 owner_id", repo="repo-taskboard"):
    response = context.client.post(
        "/api/v1/knowledge/search", json={"repo_id": repo, "query": query}
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_upload_dedup_update_delete_and_historical_preview(context):
    first = upload(context)
    assert first["version"]["status"] == "ready", first
    duplicate = upload(context, filename="copy.txt")
    assert duplicate["duplicate"] and duplicate["document_id"] == first["document_id"]
    updated = upload(context, "新的所有者策略 owner_id，不允许越权")
    assert updated["version"]["number"] == 2
    assert {v["version_id"] for v in search(context)} == {updated["version"]["id"]}
    old = context.client.get(
        f"/api/v1/knowledge/{first['document_id']}/versions/{first['version']['id']}?repo_id=repo-taskboard"
    )
    assert old.status_code == 200 and "必须隔离" in old.json()["content"]
    assert not old.json()["version"]["is_current"]
    endpoint = f"/api/v1/knowledge/{first['document_id']}/delete?repo_id=repo-taskboard"
    assert context.client.post(endpoint).status_code == 200
    assert context.client.post(endpoint).status_code == 200
    assert not search(context)
    with Session(context.engine) as session:
        assert session.scalar(select(KnowledgeChunk)) is None
        assert session.get(KnowledgeVersion, UUID(first["version"]["id"])).content


def test_failed_update_preserves_previous_effective_version(context):
    first = upload(context)
    failed = upload(context, " ")
    assert failed["version"]["status"] == "failed"
    assert failed["version"]["error_code"] == "document_empty"
    assert {v["version_id"] for v in search(context)} == {first["version"]["id"]}


def test_replacing_document_with_another_documents_content_retires_old_index(context):
    first = upload(context, "old owner_id rule", "first.md")
    second = upload(context, "new owner_id rule", "second.md")
    merged = upload(context, "new owner_id rule", "first.md")
    assert merged["duplicate"] and merged["document_id"] == second["document_id"]
    assert {hit["document_id"] for hit in search(context)} == {second["document_id"]}
    with Session(context.engine) as session:
        assert not session.get(KnowledgeVersion, UUID(first["version"]["id"])).is_current


def test_embedding_cache_reuses_identical_chunks(context):
    class CountingEmbedder(TestEmbedder):
        calls = []

        def encode(self, texts, **kwargs):
            self.calls.append(list(texts))
            return super().encode(texts, **kwargs)

    model = CountingEmbedder()
    app.dependency_overrides[embedding_factory] = lambda: lambda: model
    for text in ["a" * 384, "a" * 384 + "b" * 50]:
        response = context.client.post(
            "/api/v1/knowledge/upload",
            json={
                "repo_id": "repo-taskboard",
                "filename": "cache.txt",
                "content_base64": base64.b64encode(text.encode()).decode(),
            },
        )
        assert response.json()["version"]["status"] == "ready", response.text
    assert [len(call) for call in model.calls] == [1, 1]
    assert model.calls[1][0] == "a" * 48 + "b" * 50


@pytest.mark.parametrize("change", ["update", "delete"])
def test_index_completion_cannot_restore_deleted_or_overwrite_newer_document(context, change):
    from devflow.knowledge import upload_document

    def during_indexing():
        if change == "update":
            upload(context, "新的有效所有者策略 owner_id", "race.md")
        else:
            docs = context.client.get("/api/v1/knowledge?repo_id=repo-taskboard").json()["items"]
            context.client.post(f"/api/v1/knowledge/{docs[0]['id']}/delete?repo_id=repo-taskboard")
        return TestEmbedder()

    with Session(context.engine, expire_on_commit=False) as session:
        _, version_id, _ = upload_document(
            session,
            context.settings,
            context.store,
            "repo-taskboard",
            "race.md",
            b"old owner_id policy",
            embedder_factory=during_indexing,
        )
        assert session.get(KnowledgeVersion, version_id).error_code == "document_superseded"
    found = search(context)
    assert bool(found) == (change == "update")
    if found:
        assert all(v["version_number"] == 2 for v in found)


def test_queued_question_does_not_switch_to_later_document_version(context):
    first = upload(context)
    from devflow.config import get_settings

    settings = context.settings.model_copy(
        update={"analysis_executor": "agent", "simulation_step_seconds": 0}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    conversation = context.client.post(
        "/api/v1/conversations", json={"repo_id": "repo-taskboard", "title": "版本固定"}
    ).json()
    run = context.client.post(
        "/api/v1/runs",
        json={
            "repo_id": "repo-taskboard",
            "conversation_id": conversation["id"],
            "task_type": "knowledge_qa",
            "question": "所有者策略？",
        },
    ).json()
    assert run["input_version"]["knowledge_versions"] == [first["version"]["id"]]
    upload(context, "更新的 owner_id 策略")
    worker = Worker(context.engine, settings, context.store, embedder_factory=TestEmbedder)
    worker.execute(*worker.claim(UUID(run["id"])))
    result = context.client.get(f"/api/v1/runs/{run['id']}").json()
    assert result["status"] == "succeeded", result
    assert not result["result"]["report"]["answer_evidence"]
    assert "证据不足" in result["result"]["report"]["answer"]


def test_repository_isolation_applies_to_search_preview_and_delete(context):
    first = upload(context)
    with Session(context.engine) as session, session.begin():
        original = session.get(RepositoryRecord, "repo-taskboard")
        session.add(
            RepositoryRecord(
                id="repo-b",
                data_source="fixture",
                full_name="demo/b",
                description="B",
                language="Python",
                default_branch="main",
                default_commit=original.default_commit,
                source_updated_at=original.source_updated_at,
            )
        )
    assert not search(context, repo="repo-b")
    assert (
        context.client.get(f"/api/v1/knowledge/{first['document_id']}?repo_id=repo-b").status_code
        == 404
    )
    assert (
        context.client.post(
            f"/api/v1/knowledge/{first['document_id']}/delete?repo_id=repo-b"
        ).status_code
        == 404
    )
    assert search(context)


@pytest.mark.parametrize("has_documents", [False, True])
def test_knowledge_qa_reports_citations_or_insufficient_evidence(context, has_documents):
    if has_documents:
        upload(context)
    settings = context.settings.model_copy(
        update={"analysis_executor": "agent", "simulation_step_seconds": 0}
    )
    from devflow.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    conversation = context.client.post(
        "/api/v1/conversations", json={"repo_id": "repo-taskboard", "title": "知识问答"}
    ).json()
    response = context.client.post(
        "/api/v1/runs",
        json={
            "repo_id": "repo-taskboard",
            "conversation_id": conversation["id"],
            "task_type": "knowledge_qa",
            "question": "所有者应如何隔离？",
        },
    )
    assert response.status_code == 201, response.text
    worker = Worker(context.engine, settings, context.store, embedder_factory=TestEmbedder)
    worker.execute(*worker.claim(UUID(response.json()["id"])))
    result = context.client.get(f"/api/v1/runs/{response.json()['id']}").json()
    assert result["status"] == "succeeded", result
    report = result["result"]["report"]
    assert bool(report["answer_evidence"]) == has_documents
    if not has_documents:
        assert "证据不足" in report["answer"]
    else:
        endpoint = (
            f"/api/v1/knowledge/{upload(context)['document_id']}/delete?repo_id=repo-taskboard"
        )
        context.client.post(endpoint)
        assert context.client.get(f"/api/v1/runs/{response.json()['id']}/report").status_code == 200
        evidence = context.client.get(f"/api/v1/runs/{response.json()['id']}/evidence").json()[
            "items"
        ]
        assert report["answer_evidence"][0]["evidence_id"] in {v["id"] for v in evidence}
    with Session(context.engine) as session:
        assert session.get(RunRecord, UUID(response.json()["id"])).result["trace_artifact_id"]
