# 文件用途：验证健康检查、依赖不可用状态和错误脱敏。
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from devflow.health import ComponentHealth, HealthResponse, inspect_health
from devflow.main import app
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def test_liveness_does_not_require_database() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_failure_returns_sanitized_unavailable_response() -> None:
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("password=do-not-leak", {}, Exception("secret"))
    result = inspect_health(engine)
    assert result.status == "degraded"
    assert result.checks["database"].status == "error"
    assert result.checks["pgvector"].status == "unknown"
    assert "secret" not in result.model_dump_json()
    assert "do-not-leak" not in result.model_dump_json()


def test_readiness_http_status_matches_dependency_failure() -> None:
    failure = HealthResponse(
        status="degraded",
        checked_at=datetime.now(UTC),
        checks={"database": ComponentHealth(status="error", message="数据库不可用")},
    )
    with patch("devflow.main.inspect_health", return_value=failure), TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
