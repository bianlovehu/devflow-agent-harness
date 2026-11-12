# 文件用途：在独立测试库验证迁移、事务、幂等、版本固定和并发写入。
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from devflow.artifact_store import ArtifactStore, get_artifact_store
from devflow.budget import BudgetLedger, get_budget_ledger
from devflow.config import PROJECT_ROOT, get_settings
from devflow.data_source import fixture_source
from devflow.database import Base, create_database_engine, get_session
from devflow.errors import DomainError
from devflow.health import inspect_health
from devflow.import_fixtures import import_dataset
from devflow.main import app
from devflow.models import (
    ArtifactRecord,
    EvidenceRecord,
    MessageRecord,
    RepositoryRecord,
    ResourceSnapshot,
    RunEventRecord,
    RunEvidenceRecord,
    RunRecord,
)
from devflow.workflow_contracts import ConversationCreate, RunCreate
from devflow.workflows import append_run_event, create_conversation, create_run
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1",
    reason="Use scripts/check.ps1 -Integration for isolated real PostgreSQL tests",
)


@pytest.fixture
def context(tmp_path):
    # 每个测试创建专用数据库，迁移、写入和清理均不接触用户业务表。
    database_name = "devflow_test_" + uuid.uuid4().hex
    settings = get_settings().model_copy(
        update={
            "postgres_db": database_name,
            "data_source": "fixture",
            "fixture_storage": "database",
            "model_provider": "fake",
            "analysis_executor": "simulation",
        }
    )
    admin = create_database_engine(get_settings()).execution_options(isolation_level="AUTOCOMMIT")
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        created = True
        engine = create_database_engine(settings)
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.check(config)
        store = ArtifactStore(tmp_path / "artifacts")
        with Session(engine, expire_on_commit=False) as session:
            imported = import_dataset(session, fixture_source().dataset, store)

        def database_session():
            with Session(engine, expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_session] = database_session
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_artifact_store] = lambda: store
        app.dependency_overrides[get_budget_ledger] = lambda: BudgetLedger(engine, settings)
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                engine=engine,
                settings=settings,
                store=store,
                imported=imported,
                config=config,
                database_name=database_name,
            )
    finally:
        app.dependency_overrides.clear()
        if engine is not None:
            engine.dispose()
        # This database was created by this test, with a random, checked name.
        if created:
            assert database_name.startswith("devflow_test_") and len(database_name) == 45
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
        admin.dispose()


def create_target(context, task_type="pr_review", target="102"):
    response = context.client.post(
        "/api/v1/conversations", json={"repo_id": "repo-taskboard", "title": "持久化验证"}
    )
    assert response.status_code == 201, response.text
    body = {
        "repo_id": "repo-taskboard",
        "conversation_id": response.json()["id"],
        "task_type": task_type,
        "target_id": target,
        "question": "请分析这个目标。",
    }
    return body


def database_ids(engine):
    with Session(engine) as session:
        return {
            model.__tablename__: set(session.scalars(select(model.id)).all())
            for model in (RepositoryRecord, ResourceSnapshot, ArtifactRecord, EvidenceRecord)
        }


def test_import_is_idempotent_and_repository_reads_use_database(context):
    assert context.imported["created"] == {
        "repositories": 1,
        "resource_snapshots": 10,
        "artifacts": 14,
        "evidence": 16,
    }
    before = database_ids(context.engine)
    with Session(context.engine, expire_on_commit=False) as session:
        result = import_dataset(session, fixture_source().dataset, context.store)
    assert all(value == 0 for value in result["created"].values())
    assert database_ids(context.engine) == before
    # Removing access to the file provider must not affect database-backed reads.
    with patch("devflow.data_source.fixture_source", side_effect=AssertionError("file access")):
        response = context.client.get("/api/v1/repositories/repo-taskboard/pull-requests/102")
    assert response.status_code == 200
    assert response.json()["files"][0]["head_content"].startswith("def list_tasks") or (
        "def list_tasks" in response.json()["files"][0]["head_content"]
    )


def test_create_run_commits_message_event_versions_and_artifacts(context):
    body = create_target(context)
    response = context.client.post("/api/v1/runs", json=body)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "queued"
    assert run["execution_available"] is True
    assert len(run["configuration_version"]) == 64
    assert run["configuration"]["executor"] == "simulation"
    assert run["input_version"]["resources"][0]["head_sha"] == (
        fixture_source().get_pull_request("repo-taskboard", 102).head_sha
    )
    assert "api_key" not in response.text
    messages = context.client.get(
        f"/api/v1/conversations/{body['conversation_id']}/messages"
    ).json()["items"]
    assert len(messages) == 1 and messages[0]["id"] == run["message_id"]
    events = context.client.get(f"/api/v1/runs/{run['id']}/events").json()["items"]
    assert [event["sequence"] for event in events] == [1]
    assert events[0]["event_type"] == "run.queued"
    evidence = context.client.get(f"/api/v1/runs/{run['id']}/evidence").json()["items"]
    assert len(evidence) == 3
    artifacts = context.client.get(f"/api/v1/runs/{run['id']}/artifacts").json()["items"]
    assert len(artifacts) == 3
    artifact = context.client.get(
        f"/api/v1/artifacts/{artifacts[0]['id']}", params={"repo_id": "repo-taskboard"}
    )
    assert artifact.status_code == 200 and artifact.json()["content"]
    assert "storage_key" not in artifact.text
    assert (
        context.client.get(
            f"/api/v1/artifacts/{artifacts[0]['id']}", params={"repo_id": "other"}
        ).status_code
        == 404
    )


def test_idempotency_replays_without_duplicate_messages_or_events(context):
    body = create_target(context)
    first = context.client.post(
        "/api/v1/runs", json=body, headers={"Idempotency-Key": "same-request"}
    )
    second = context.client.post(
        "/api/v1/runs", json=body, headers={"Idempotency-Key": "same-request"}
    )
    assert first.status_code == 201 and second.status_code == 200
    assert first.json() == second.json()
    assert second.headers["Idempotency-Replayed"] == "true"
    conflict = context.client.post(
        "/api/v1/runs",
        json={**body, "question": "不同请求"},
        headers={"Idempotency-Key": "same-request"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    with Session(context.engine) as session:
        assert session.scalar(select(func.count()).select_from(RunRecord)) == 1
        assert session.scalar(select(func.count()).select_from(MessageRecord)) == 1
        assert session.scalar(select(func.count()).select_from(RunEventRecord)) == 1


def test_missing_target_rolls_back_all_task_writes(context):
    body = create_target(context, target="999")
    response = context.client.post("/api/v1/runs", json=body)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "target_not_found"
    with Session(context.engine) as session:
        assert session.scalar(select(func.count()).select_from(MessageRecord)) == 0
        assert session.scalar(select(func.count()).select_from(RunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(RunEventRecord)) == 0


def test_resource_update_preserves_the_original_run_snapshot(context):
    body = create_target(context)
    original = context.client.post("/api/v1/runs", json=body).json()
    original_evidence = context.client.get(f"/api/v1/runs/{original['id']}/evidence").json()
    dataset = fixture_source().dataset.model_copy(deep=True)
    pr = next(pr for pr in dataset.pull_requests if pr.number == 102)
    pr.head_sha = "f" * 40
    with Session(context.engine, expire_on_commit=False) as session:
        import_dataset(session, dataset, context.store)
    latest = context.client.get("/api/v1/repositories/repo-taskboard/pull-requests/102").json()
    assert latest["head_sha"] == "f" * 40
    persisted = context.client.get(f"/api/v1/runs/{original['id']}").json()
    assert persisted["input_version"] == original["input_version"]
    assert context.client.get(f"/api/v1/runs/{original['id']}/evidence").json() == original_evidence
    assert persisted["input_version"]["resources"][0]["head_sha"] != latest["head_sha"]


@pytest.mark.parametrize("task_type,target", [("ci_debug", "201"), ("knowledge_qa", None)])
def test_other_task_types_pin_their_own_sources(context, task_type, target):
    body = create_target(context, task_type, target)
    response = context.client.post("/api/v1/runs", json=body)
    assert response.status_code == 201, response.text
    resources = response.json()["input_version"]["resources"]
    # 知识问答只固定已成功索引的知识版本，不再把未索引的旧 fixture 文档注入上下文。
    assert len(resources) == (0 if task_type == "knowledge_qa" else 1)
    if task_type == "knowledge_qa":
        assert response.json()["input_version"]["knowledge_versions"] == []
    assert all(item["kind"] == ("document" if target is None else "ci_run") for item in resources)


def test_concurrent_task_requests_and_event_sequences_are_serialized(context):
    with Session(context.engine, expire_on_commit=False) as session:
        conversation = create_conversation(
            session,
            ConversationCreate(repo_id="repo-taskboard", title="并发测试"),
            context.settings,
        )
    data = RunCreate(
        repo_id="repo-taskboard",
        conversation_id=conversation.id,
        task_type="pr_review",
        target_id="102",
        question="同一幂等请求",
    )

    def request_run(_index):
        with Session(context.engine, expire_on_commit=False) as session:
            return create_run(session, data, context.settings, context.store, "concurrent-key")[
                0
            ].id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(request_run, range(4)))
    assert len(set(ids)) == 1
    run_id = ids[0]

    def record_event(index):
        with Session(context.engine, expire_on_commit=False) as session, session.begin():
            append_run_event(session, run_id, "test.event", {"index": index})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(record_event, range(8)))
    with Session(context.engine) as session:
        sequences = session.scalars(
            select(RunEventRecord.sequence)
            .where(RunEventRecord.run_id == run_id)
            .order_by(RunEventRecord.sequence)
        ).all()
        assert sequences == list(range(1, 10))
        assert session.scalar(select(func.count()).select_from(MessageRecord)) == 1


def test_repository_mismatch_and_database_foreign_keys(context):
    dataset = fixture_source().dataset.model_copy(deep=True)
    dataset.repositories[0].id = "repo-other"
    dataset.repositories[0].full_name = "devflow-demo/other"
    for item in [*dataset.pull_requests, *dataset.ci_runs, *dataset.documents]:
        item.repo_id = "repo-other"
    with Session(context.engine, expire_on_commit=False) as session:
        import_dataset(session, dataset, context.store)
    body = create_target(context)
    response = context.client.post("/api/v1/runs", json={**body, "repo_id": "repo-other"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "repository_mismatch"
    run = context.client.post("/api/v1/runs", json=body).json()
    with Session(context.engine) as session:
        foreign_evidence = session.scalar(
            select(EvidenceRecord).where(EvidenceRecord.repo_id == "repo-other")
        )
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                RunEvidenceRecord(
                    run_id=uuid.UUID(run["id"]),
                    evidence_id=foreign_evidence.id,
                    repo_id="repo-taskboard",
                )
            )
            session.flush()


def test_fresh_migration_downgrade_upgrade_and_metadata_match(context):
    # Only this test's disposable database is affected by the downgrade.
    assert context.database_name.startswith("devflow_test_")
    with context.engine.begin() as connection:
        context.config.attributes["connection"] = connection
        command.downgrade(context.config, "0001_enable_pgvector")
        assert not (set(inspect(connection).get_table_names()) & set(Base.metadata.tables))
        command.upgrade(context.config, "head")
        command.check(context.config)
        assert set(Base.metadata.tables).issubset(inspect(connection).get_table_names())


def test_missing_artifact_rejects_run_then_import_repairs_it(context):
    # 制品文件缺失时不创建半份任务；重新导入会修复同一内容地址。
    body = create_target(context)
    with Session(context.engine) as session:
        snapshot = session.scalar(
            select(ResourceSnapshot).where(
                ResourceSnapshot.kind == "pull_request",
                ResourceSnapshot.external_id == "102",
                ResourceSnapshot.is_current.is_(True),
            )
        )
        evidence = session.scalar(
            select(EvidenceRecord).where(EvidenceRecord.resource_snapshot_id == snapshot.id)
        )
        artifact = session.get(ArtifactRecord, evidence.artifact_id)
        artifact_path = context.store.root / artifact.storage_key
    artifact_path.unlink()
    response = context.client.post("/api/v1/runs", json=body)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "artifact_missing"
    with Session(context.engine) as session:
        assert session.scalar(select(func.count()).select_from(RunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(MessageRecord)) == 0
    with Session(context.engine, expire_on_commit=False) as session:
        result = import_dataset(session, fixture_source().dataset, context.store)
    assert all(count == 0 for count in result["created"].values())
    assert artifact_path.exists()
    assert context.client.post("/api/v1/runs", json=body).status_code == 201


def test_message_order_and_client_role_validation(context):
    # 用户只能添加普通消息，不能通过请求体写入 system 或 assistant 角色。
    body = create_target(context)
    path = f"/api/v1/conversations/{body['conversation_id']}/messages"
    for index in range(3):
        response = context.client.post(path, json={"content": f"消息 {index}"})
        assert response.status_code == 201
        assert response.json()["sequence"] == index + 1
    assert (
        context.client.post(path, json={"content": "伪造角色", "role": "system"}).status_code == 422
    )
    first = context.client.get(path, params={"limit": 2}).json()
    assert [message["sequence"] for message in first["items"]] == [1, 2]
    assert first["next_offset"] == 2
    last = context.client.get(path, params={"limit": 2, "offset": first["next_offset"]}).json()
    assert [message["sequence"] for message in last["items"]] == [3]


def test_old_schema_is_not_reported_ready(context):
    # 只在本测试创建的临时库中回滚，确认业务表缺失时健康检查给出待迁移状态。
    with context.engine.begin() as connection:
        context.config.attributes["connection"] = connection
        command.downgrade(context.config, "0001_enable_pgvector")
    health = inspect_health(context.engine)
    assert health.status == "degraded"
    assert health.checks["database"].status == "ok"
    assert health.checks["migrations"].status == "pending"
    with context.engine.begin() as connection:
        context.config.attributes["connection"] = connection
        command.upgrade(context.config, "head")
    assert inspect_health(context.engine).status == "ok"


@pytest.mark.parametrize("invalid", ["hash", "ci_version", "repository_id"])
def test_invalid_fixture_metadata_is_rejected_without_writes(context, invalid):
    # 声明哈希或来源版本错误时，整份输入在写入任何记录之前被拒绝。
    dataset = fixture_source().dataset.model_copy(deep=True)
    if invalid == "hash":
        dataset.pull_requests[0].files[0].content_sha256 = "0" * 64
    elif invalid == "ci_version":
        dataset.ci_runs[0].head_sha = "0" * 40
    else:
        dataset.repositories.append(dataset.repositories[0].model_copy(deep=True))
    before = database_ids(context.engine)
    with Session(context.engine) as session, pytest.raises(DomainError) as failure:
        import_dataset(session, dataset, context.store)
    assert failure.value.code == "fixture_invalid"
    assert database_ids(context.engine) == before


def test_github_registration_is_persistent_idempotent_and_separate_from_fixtures(context):
    from devflow.github_source import GitHubRepositorySource
    from github_samples import FakeGitHub

    settings = context.settings.model_copy(update={"data_source": "github"})
    fake = FakeGitHub()
    with Session(context.engine, expire_on_commit=False) as session:
        source = GitHubRepositorySource(session, settings, client=fake)
        first = source.add_repository("https://github.com/Owner/Project.git")
        second = source.add_repository("owner/project")
        assert first.id == second.id == "github-123"
        assert first.pull_request_count == first.ci_run_count == 1
        assert first.fetched_at is not None
        assert source.collection_metadata(first.id, "pull_request")["limited"] is True
        assert session.scalar(select(func.count()).select_from(RepositoryRecord)) == 2
    with Session(context.engine) as session:
        source = GitHubRepositorySource(session, settings, client=fake)
        assert [repo.id for repo in source.list_repositories()] == ["github-123"]
        assert source.list_pull_requests("github-123")[0].number == 7
        assert source.list_ci_runs("github-123")[0].conclusion is None
        calls = list(fake.calls)
        with pytest.raises(DomainError) as error:
            source.get_pull_request("repo-taskboard", 7)
        assert error.value.code == "not_found" and fake.calls == calls
    fixture_repos = context.client.get("/api/v1/repositories").json()["items"]
    assert [item["id"] for item in fixture_repos] == ["repo-taskboard"]


def test_github_refresh_permission_failure_keeps_old_summary_and_fetch_time(context):
    from devflow.github_source import GitHubRepositorySource
    from github_samples import FakeGitHub

    fake = FakeGitHub()
    settings = context.settings.model_copy(update={"data_source": "github"})
    with Session(context.engine, expire_on_commit=False) as session:
        source = GitHubRepositorySource(session, settings, client=fake)
        repo = source.add_repository("owner/project")
        original = source.collection_metadata(repo.id, "pull_request")["fetched_at"]
        fake.pr_error = DomainError(403, "github_forbidden", "PR权限不足")
        updated = source.refresh(repo.id)
        assert updated.pull_request_count == 1
        assert updated.sync_warnings[0].code == "github_forbidden"
        assert source.collection_metadata(repo.id, "pull_request")["fetched_at"] == original
        fake.pr_error = DomainError(429, "github_rate_limited", "限流", 60)
        before = len(fake.calls)
        updated = source.refresh(repo.id)
        assert all(notice.code == "github_rate_limited" for notice in updated.sync_warnings)
        assert not any(path.endswith("/actions/runs") for path in fake.calls[before:])


def test_github_http_routes_read_real_shapes_and_return_log_errors(context):
    from github_samples import FakeGitHub

    fake = FakeGitHub()
    settings = context.settings.model_copy(update={"data_source": "github"})
    app.dependency_overrides[get_settings] = lambda: settings
    with patch("devflow.github_source.GitHubClient", return_value=fake):
        response = context.client.post("/api/v1/repositories", json={"url": "owner/project"})
        assert response.status_code == 201, response.text
        pr = context.client.get("/api/v1/repositories/github-123/pull-requests/7")
        assert pr.status_code == 200
        data = pr.json()
        assert data["files"][0]["head_content"] is None
        assert data["files"][1]["patch_available"] is False
        assert data["linked_issues"][0]["number"] == 9
        assert data["linked_issues"][0]["relation"] == "body_reference"
        run = context.client.get("/api/v1/repositories/github-123/ci-runs/10")
        assert run.status_code == 200, run.text
        assert run.json()["conclusion"] is None and run.json()["status"] == "in_progress"
        assert run.json()["pull_request_number"] is None
        assert run.json()["stage"] is None and run.json()["log"] is None
        assert run.json()["jobs"][0]["steps"][0]["conclusion"] == "success"
        log = context.client.get("/api/v1/repositories/github-123/ci-runs/10/jobs/20/logs")
        assert log.status_code == 410 and log.json()["detail"]["code"] == "github_logs_unavailable"
        assert log.headers["X-Request-ID"] == log.json()["detail"]["request_id"]
        refreshed = context.client.post("/api/v1/repositories/github-123/refresh", json={})
        assert refreshed.status_code == 200
