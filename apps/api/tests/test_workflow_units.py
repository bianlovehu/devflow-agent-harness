# 文件用途：验证制品完整性、任务参数、请求来源和错误脱敏。
import hashlib
from unittest.mock import patch
from uuid import uuid4

import pytest
from devflow.artifact_store import ArtifactStore
from devflow.database import get_session
from devflow.errors import DomainError
from devflow.main import app
from devflow.workflow_contracts import RunCreate
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError


def test_artifact_bytes_hash_crlf_and_corruption_detection(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    key, digest, size = store.put_text("first\nsecond\n")
    data = (store.root / key).read_bytes()
    assert data == b"first\r\nsecond\r\n"
    assert hashlib.sha256(data).hexdigest() == digest
    assert len(data) == size
    assert store.put_text("first\r\nsecond\r\n") == (key, digest, size)
    (store.root / key).write_bytes(b"corrupt")
    with pytest.raises(DomainError, match="引用的制品校验失败"):
        store.read_text(key, digest)


def test_artifact_paths_cannot_escape_store(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    with pytest.raises(DomainError):
        store.read_text("../../outside.txt", "f" * 64)


def test_task_target_and_budget_validation():
    body = {
        "repo_id": "repo-taskboard",
        "conversation_id": str(uuid4()),
        "task_type": "pr_review",
        "target_id": "00102",
        "question": "  检查变更  ",
    }
    validated = RunCreate.model_validate(body)
    assert validated.target_id == "102"
    assert validated.question == "检查变更"
    with pytest.raises(ValidationError):
        RunCreate.model_validate({**body, "target_id": "../secret"})
    with pytest.raises(ValidationError):
        RunCreate.model_validate({**body, "budget": {"max_model_calls": 0}})
    with pytest.raises(ValidationError):
        RunCreate.model_validate({**body, "task_type": "knowledge_qa"})


def test_cross_origin_write_rejected_before_database():
    with patch("devflow.workflows.create_conversation") as create, TestClient(app) as client:
        response = client.post(
            "/api/v1/conversations",
            json={"repo_id": "repo-taskboard", "title": "test"},
            headers={"Origin": "https://untrusted.example"},
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_denied"
    create.assert_not_called()


def test_validation_response_omits_untrusted_input():
    with TestClient(app) as client:
        response = client.post("/api/v1/runs", json={"private-input": "do-not-echo"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
    assert "do-not-echo" not in response.text
    assert response.json()["detail"]["request_id"] == response.headers["X-Request-ID"]


def test_database_error_response_omits_connection_details():
    def broken_session():
        raise OperationalError("password=do-not-echo", {}, Exception("sensitive"))
        yield

    app.dependency_overrides[get_session] = broken_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/conversations", params={"repo_id": "repo-taskboard"})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "database_unavailable"
        assert "do-not-echo" not in response.text
        assert "sensitive" not in response.text
    finally:
        app.dependency_overrides.clear()
