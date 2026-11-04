# 文件用途：在真实隔离数据库验证固定证据、worker 并发/取消/租约，以及 SSE 重放。
import asyncio
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import test_persistence_integration as persistence
from devflow.config import get_settings
from devflow.errors import DomainError
from devflow.event_stream import stream_events
from devflow.github_source import GitHubRepositorySource
from devflow.main import app
from devflow.models import ArtifactRecord, ResourceSnapshot, RunEventRecord, RunRecord
from devflow.worker import LeaseLost, Worker
from devflow.workflows import append_run_event
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_fixed_files import EvidenceGitHub
from test_persistence_integration import create_target

context = persistence.context

pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1", reason="isolated PostgreSQL required"
)


def worker(context, **kwargs):
    settings = context.settings.model_copy(update={"simulation_step_seconds": 0})
    return Worker(context.engine, settings, context.store, **kwargs)


def make_run(context):
    response = context.client.post(
        "/api/v1/runs", json=create_target(context), headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def read(context, run_id):
    response = context.client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def event_types(context, run_id):
    return [
        row["event_type"]
        for row in context.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    ]


def test_concurrent_workers_claim_once_and_finish_persisted_simulation(context):
    run_id = make_run(context)
    first, second = worker(context), worker(context)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda candidate: candidate.claim(), [first, second]))
    assert sum(claim is not None for claim in claims) == 1
    index = next(i for i, claim in enumerate(claims) if claim is not None)
    [first, second][index].execute(*claims[index])
    result = read(context, run_id)
    assert result["status"] == "succeeded"
    assert result["result"]["model_calls"] == 0
    assert result["result"]["analysis_report_available"] is False
    assert result["attempt"] == 1
    types = event_types(context, run_id)
    assert types.count("run.started") == types.count("run.succeeded") == 1
    # 新 API 客户端直接读持久化结果，不依赖原页面或 worker 的内存状态。
    with Session(context.engine) as session:
        assert session.get(RunRecord, run_id).status == "succeeded"


def test_queued_cancel_is_idempotent_and_never_claimed(context):
    run_id = make_run(context)
    for _ in range(2):
        assert context.client.post(f"/api/v1/runs/{run_id}/cancel").json()["status"] == "cancelled"
    assert worker(context).claim() is None
    assert event_types(context, run_id) == ["run.queued", "run.cancel_requested", "run.cancelled"]


def test_cancel_during_long_step_does_not_enter_next_stage(context):
    run_id = make_run(context)
    candidate = worker(context)
    candidate.settings = candidate.settings.model_copy(update={"simulation_step_seconds": 2})
    claimed = candidate.claim()
    reached = threading.Event()
    original_wait = candidate._wait

    def waiting(*args):
        reached.set()
        original_wait(*args)

    candidate._wait = waiting
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(candidate.execute, *claimed)
        assert reached.wait(5)
        context.client.post(f"/api/v1/runs/{run_id}/cancel")
        running.result(timeout=5)
    assert read(context, run_id)["status"] == "cancelled"
    assert "tool.started" not in event_types(context, run_id)
    assert "stage.completed" not in event_types(context, run_id)


def test_expired_lease_fences_old_owner_and_retry_keeps_evidence(context):
    run_id = make_run(context)
    candidate = worker(context)
    _, token = candidate.claim()
    candidate.heartbeat(run_id, token)
    with Session(context.engine) as session, session.begin():
        run = session.get(RunRecord, run_id)
        assert run.heartbeat_at and run.lease_expires_at > run.heartbeat_at
        run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert worker(context).reap_expired() == 1
    assert read(context, run_id)["error_code"] == "worker_lost"
    with pytest.raises(LeaseLost):
        candidate._finish(run_id, token, "succeeded")
    with pytest.raises(LeaseLost):
        candidate.heartbeat(run_id, token)
    headers = {"Idempotency-Key": "manual-retry"}
    first = context.client.post(f"/api/v1/runs/{run_id}/retry", headers=headers)
    second = context.client.post(f"/api/v1/runs/{run_id}/retry", headers=headers)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    retried = first.json()
    assert retried["retry_of"] == str(run_id)
    assert retried["input_version"] == read(context, run_id)["input_version"]
    before = context.client.get(f"/api/v1/runs/{run_id}/evidence").json()
    after = context.client.get(f"/api/v1/runs/{retried['id']}/evidence").json()
    assert before == after
    assert worker(context).run_once()
    assert read(context, retried["id"])["status"] == "succeeded"
    assert read(context, run_id)["status"] == "needs_attention"


def test_expired_cancelled_worker_is_reaped_as_cancelled(context):
    run_id = make_run(context)
    candidate = worker(context)
    candidate.claim()
    context.client.post(f"/api/v1/runs/{run_id}/cancel")
    with Session(context.engine) as session, session.begin():
        session.get(RunRecord, run_id).lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert candidate.reap_expired() == 1
    assert read(context, run_id)["status"] == "cancelled"


def test_stale_token_cannot_write_even_with_live_lease(context):
    run_id = make_run(context)
    candidate = worker(context)
    _, token = candidate.claim()
    with Session(context.engine) as session, session.begin():
        session.get(RunRecord, run_id).lease_token = uuid.uuid4()
    with pytest.raises(LeaseLost):
        candidate._event(run_id, token, "stage.completed", {})
    assert event_types(context, run_id) == ["run.queued", "run.started"]


def test_missing_artifact_fails_once_and_timeout_stops_before_stage(context):
    run_id = make_run(context)
    evidence = context.client.get(f"/api/v1/runs/{run_id}/evidence").json()["items"][0]
    with Session(context.engine) as session:
        artifact = session.get(ArtifactRecord, uuid.UUID(evidence["artifact_id"]))
        (context.store.root / artifact.storage_key).unlink()
    candidate = worker(context)
    assert candidate.run_once()
    assert read(context, run_id)["status"] == "failed"
    assert read(context, run_id)["error_code"] == "artifact_missing"
    assert candidate.claim() is None
    assert event_types(context, run_id).count("run.failed") == 1


def test_execution_timeout_is_persisted(context):
    run_id = make_run(context)
    candidate = worker(context)
    claimed = candidate.claim()
    with Session(context.engine) as session, session.begin():
        session.get(RunRecord, run_id).started_at = datetime.now(UTC) - timedelta(seconds=601)
    candidate.execute(*claimed)
    assert read(context, run_id)["error_code"] == "timeout"
    assert "stage.started" not in event_types(context, run_id)


def test_sse_replays_every_persisted_event_after_cursor_across_batches(context):
    run_id = make_run(context)
    with Session(context.engine) as session, session.begin():
        for i in range(220):
            append_run_event(session, run_id, "stage.completed", {"number": i})
    context.client.post(f"/api/v1/runs/{run_id}/cancel")
    response = context.client.get(
        f"/api/v1/runs/{run_id}/stream?after=1", headers={"Last-Event-ID": "50"}
    )
    assert response.status_code == 200 and response.headers["content-type"].startswith(
        "text/event-stream"
    )
    ids = [int(line[4:]) for line in response.text.splitlines() if line.startswith("id: ")]
    with Session(context.engine) as session:
        expected = session.scalars(
            select(RunEventRecord.sequence)
            .where(RunEventRecord.run_id == run_id, RunEventRecord.sequence > 50)
            .order_by(RunEventRecord.sequence)
        ).all()
    assert ids == expected
    assert "event: end" in response.text
    again = context.client.get(
        f"/api/v1/runs/{run_id}/stream", headers={"Last-Event-ID": str(ids[-1])}
    )
    assert "id: " not in again.text and "event: end" in again.text
    assert (
        context.client.get(
            f"/api/v1/runs/{run_id}/stream", headers={"Last-Event-ID": "-1"}
        ).status_code
        == 422
    )


def test_stream_disconnect_does_not_cancel_run(context):
    run_id = make_run(context)

    class Request:
        closed = False

        async def is_disconnected(self):
            return self.closed

    request = Request()

    async def disconnect():
        stream = stream_events(request, context.engine, run_id, 0)
        assert "retry:" in await anext(stream)
        assert "id: 1" in await anext(stream)
        request.closed = True
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(disconnect())
    assert read(context, run_id)["status"] == "queued"
    assert read(context, run_id)["cancel_requested_at"] is None


def github_run(context, task_type="pr_review", target="7"):
    settings = context.settings.model_copy(
        update={"data_source": "github", "simulation_step_seconds": 0}
    )
    fake = EvidenceGitHub()
    with Session(context.engine, expire_on_commit=False) as session:
        GitHubRepositorySource(session, settings, fake).add_repository("owner/project")
    app.dependency_overrides[get_settings] = lambda: settings
    conversation = context.client.post(
        "/api/v1/conversations", json={"repo_id": "github-123", "title": "固定真实来源证据"}
    ).json()
    created = context.client.post(
        "/api/v1/runs",
        json={
            "repo_id": "github-123",
            "conversation_id": conversation["id"],
            "task_type": task_type,
            "target_id": target,
            "question": "核查固定证据",
        },
    )
    assert created.status_code == 201, created.text
    return settings, fake, uuid.UUID(created.json()["id"])


def test_github_worker_pins_artifacts_and_old_run_survives_pr_changes(context):
    settings, fake, run_id = github_run(context)
    candidate = Worker(context.engine, settings, context.store, client_factory=lambda _: fake)
    assert candidate.run_once()
    original = read(context, run_id)
    assert original["status"] == "succeeded", original
    evidence = context.client.get(f"/api/v1/runs/{run_id}/evidence").json()
    assert any(
        row["source_type"] == "file" and row["version"] == "b" * 40 for row in evidence["items"]
    )
    fake.head = "c" * 40
    with Session(context.engine, expire_on_commit=False) as session:
        source = GitHubRepositorySource(session, settings, fake)
        source.refresh("github-123")
        assert source.list_pull_requests("github-123")[0].head_sha == "c" * 40
    next_response = context.client.post(
        "/api/v1/runs",
        json={
            "repo_id": "github-123",
            "conversation_id": original["conversation_id"],
            "task_type": "pr_review",
            "target_id": "7",
            "question": "核查更新后的提交",
        },
    )
    assert next_response.status_code == 201
    assert candidate.run_once()
    assert (
        read(context, next_response.json()["id"])["input_version"]["resources"][0]["head_sha"]
        == "c" * 40
    )
    assert read(context, run_id)["input_version"] == original["input_version"]
    assert context.client.get(f"/api/v1/runs/{run_id}/evidence").json() == evidence
    for row in evidence["items"]:
        assert (
            context.client.get(
                f"/api/v1/artifacts/{row['artifact_id']}?repo_id=github-123"
            ).status_code
            == 200
        )
    with Session(context.engine) as session:
        snapshot = session.get(
            ResourceSnapshot, uuid.UUID(original["input_version"]["resources"][0]["snapshot_id"])
        )
        assert snapshot.payload["coverage"][0]["supplemented"] is True
        assert snapshot.is_current is False
        assert snapshot.payload["head_sha"] == "b" * 40


def test_github_pr_movement_fails_without_binding_mixed_evidence(context):
    settings, fake, run_id = github_run(context)
    fake.move_after_files = True
    assert Worker(context.engine, settings, context.store, client_factory=lambda _: fake).run_once()
    assert read(context, run_id)["error_code"] == "input_changed"
    assert context.client.get(f"/api/v1/runs/{run_id}/evidence").json()["items"] == []


def test_github_ci_attempt_log_is_saved_with_job_identity_and_sha(context):
    settings, fake, run_id = github_run(context, "ci_debug", "10")
    assert Worker(context.engine, settings, context.store, client_factory=lambda _: fake).run_once()
    result = read(context, run_id)
    assert result["status"] == "succeeded", result
    rows = context.client.get(f"/api/v1/runs/{run_id}/evidence").json()["items"]
    log = next(row for row in rows if row["source_type"] == "log")
    assert "attempt-2/job-20.log" in log["path"] and "attempt-2:job-20" in log["version"]
    with Session(context.engine) as session:
        record = session.get(ArtifactRecord, uuid.UUID(log["artifact_id"]))
        assert (context.store.root / record.storage_key).read_bytes() == fake.raw_log


def test_github_expired_logs_preserve_metadata_and_require_attention(context):
    settings, fake, run_id = github_run(context, "ci_debug", "10")

    def expired(*_):
        raise DomainError(410, "github_logs_unavailable", "日志已过期")

    fake.raw_job_log = expired
    assert Worker(context.engine, settings, context.store, client_factory=lambda _: fake).run_once()
    assert read(context, run_id)["status"] == "needs_attention"
    assert read(context, run_id)["error_code"] == "evidence_unavailable"
    assert context.client.get(f"/api/v1/runs/{run_id}/evidence").json()["items"]


def test_terminal_commit_between_stream_queries_cannot_drop_final_events(context, monkeypatch):
    from devflow.event_stream import event_batch
    from devflow.workflows import cancel_run

    run_id = make_run(context)
    raced = False

    class RacingSession(Session):
        def scalars(self, *args, **kwargs):
            nonlocal raced
            result = super().scalars(*args, **kwargs)
            # 模拟事件查询完成后、stream发送响应前，另一个事务提交终态与结束事件。
            if not raced:
                raced = True
                with Session(context.engine, expire_on_commit=False) as writer:
                    cancel_run(writer, run_id)
            return result

    monkeypatch.setattr("devflow.event_stream.Session", RacingSession)
    first, status = event_batch(context.engine, run_id, 0)
    assert [row["sequence"] for row in first] == [1]
    assert status == "queued"  # 仍须继续取下一批，不能过早发送 end。
    remaining, status = event_batch(context.engine, run_id, 1)
    assert [row["sequence"] for row in remaining] == [2, 3]
    assert status == "cancelled"
