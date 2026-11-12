# 文件用途：验证显式checkpoint迁移、部署心跳、缺失权重不联网和源码发布包边界。
import os
import time

import pytest
from devflow.healthcheck import check_worker, worker_heartbeat


def test_local_artifact_directory_isolated_without_changing_project_root(tmp_path, monkeypatch):
    from devflow.artifact_store import ArtifactStore, get_artifact_store

    monkeypatch.setenv("DEVFLOW_ARTIFACT_ROOT", str(tmp_path / "isolated"))
    store = get_artifact_store()
    key, digest, _ = store.put_text("本地隔离验证\n")
    assert store.root == (tmp_path / "isolated").resolve()
    assert store.read_text(key, digest) == "本地隔离验证\r\n"
    assert ArtifactStore(tmp_path / "explicit").root == (tmp_path / "explicit").resolve()


def test_worker_health_tracks_polling_and_rejects_stale_heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat.json"
    monkeypatch.setenv("DEVFLOW_WORKER_HEARTBEAT", str(path))
    worker_heartbeat()
    assert check_worker(path)
    monkeypatch.setattr(time, "time", lambda: 999999999999)
    assert not check_worker(path)


def test_missing_local_embeddings_fail_before_network(tmp_path, monkeypatch):
    import devflow.embeddings as embeddings
    from devflow.errors import DomainError

    monkeypatch.setattr(embeddings, "MODEL_DIR", tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("runtime download"))
    with pytest.raises(DomainError) as exc:
        embeddings.LocalEmbedder()
    assert exc.value.code == "embedding_not_ready"


@pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1", reason="isolated PostgreSQL required"
)
def test_explicit_migration_initializes_checkpoint_and_worker_never_calls_setup(
    tmp_path, monkeypatch
):
    import test_persistence_integration as persistence
    from devflow.worker import Worker
    from langgraph.checkpoint.postgres import PostgresSaver
    from sqlalchemy import text

    # 复用已验证的专用数据库fixture，最终不会影响日常业务库。
    fixture = persistence.context.__wrapped__(tmp_path)
    context = next(fixture)
    try:
        with context.engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT max(v) FROM devflow_checkpoints.checkpoint_migrations")
                )
                == 9
            )
        monkeypatch.setattr(PostgresSaver, "setup", lambda self: pytest.fail("runtime DDL"))
        from test_week05_integration import create_agent_run

        run, _ = create_agent_run(context)
        worker = Worker(
            context.engine,
            context.settings.model_copy(update={"analysis_executor": "agent"}),
            context.store,
        )
        from uuid import UUID

        worker.execute(*worker.claim(UUID(run["id"])))
        assert context.client.get(f"/api/v1/runs/{run['id']}").json()["status"] == "succeeded"
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
