# 文件用途：验证部署验收脚本按当前记忆索引流程批准经验，并在索引失败时停止。
import importlib.util
from uuid import UUID

import pytest
import test_persistence_integration as persistence
from devflow.core.config import PROJECT_ROOT, get_settings
from devflow.knowledge.api import embedding_factory
from devflow.main import app
from devflow.workflows.worker import Worker
from test_week04_integration import TestEmbedder, upload

context = persistence.context
pytestmark = persistence.pytestmark


@pytest.mark.parametrize("index_available", [True, False])
def test_release_smoke_memory_index_and_persistence(context, monkeypatch, index_available):
    spec = importlib.util.spec_from_file_location(
        "release_smoke", PROJECT_ROOT / "scripts/release_smoke.py"
    )
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    settings = context.settings.model_copy(
        update={"analysis_executor": "agent", "simulation_step_seconds": 0}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    upload(context, "任务所有者 owner_id 必须隔离，labels 需要保留列表约束。")

    def unavailable_embedder():
        raise RuntimeError("index unavailable")

    app.dependency_overrides[embedding_factory] = lambda: (
        TestEmbedder if index_available else unavailable_embedder
    )
    worker = Worker(context.engine, settings, context.store, embedder_factory=TestEmbedder)
    approval_requests = []

    def request(base, path, body=None):
        method = "GET" if body is None else "POST"
        if "/approve?" in path:
            approval_requests.append(path)
        response = context.client.request(
            method, path, **({"json": body} if body is not None else {})
        )
        response.raise_for_status()
        result = response.json()
        if method == "POST" and path == "/api/v1/runs":
            worker.execute(*worker.claim(UUID(result["id"])))
        return result

    monkeypatch.setattr(smoke, "request", request)
    if index_available:
        proof = smoke.create("http://fixture")
        assert len(approval_requests) == 1
        context.engine.dispose()
        smoke.verify("http://fixture", proof)
    else:
        with pytest.raises(RuntimeError, match="记忆索引未就绪"):
            smoke.create("http://fixture")
        assert not approval_requests
        memories = context.client.get("/api/v1/memories?repo_id=repo-taskboard").json()["items"]
        assert len(memories) == 1
        assert memories[0]["status"] == "pending"
        assert memories[0]["index_status"] == "failed"
