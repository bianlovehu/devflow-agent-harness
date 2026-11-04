# 文件用途：在隔离 PostgreSQL 中验证第三周报告、失败与取消，以及报告导出。
import json
import os
from uuid import UUID

import pytest
import test_persistence_integration as persistence
from devflow.config import get_settings
from devflow.model_gateway import ModelError, ScriptedModel
from devflow.models import ArtifactRecord, RunRecord
from devflow.worker import Worker
from sqlalchemy.orm import Session
from test_persistence_integration import create_target

context = persistence.context

pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1", reason="isolated PostgreSQL required"
)


def agent_run(context, task="pr_review", target="102", model_factory=None):
    settings = context.settings.model_copy(
        update={
            "analysis_executor": "agent",
            "model_provider": "fake",
            "simulation_step_seconds": 0,
        }
    )
    from devflow.main import app

    app.dependency_overrides[get_settings] = lambda: settings
    response = context.client.post("/api/v1/runs", json=create_target(context, task, target))
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"]), Worker(
        context.engine, settings, context.store, model_factory=model_factory
    )


@pytest.mark.parametrize(
    "task,target,expected",
    [
        ("pr_review", "101", 0),
        ("pr_review", "102", 1),
        ("pr_review", "103", 1),
        ("ci_debug", "201", 1),
        ("ci_debug", "202", 1),
        ("ci_debug", "203", 1),
    ],
)
def test_fixture_agent_reports_are_persisted_and_exportable(context, task, target, expected):
    run_id, worker = agent_run(context, task, target)
    assert worker.run_once()
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "succeeded", result
    assert result["result"]["provider"] == "fake"
    report = context.client.get(f"/api/v1/runs/{run_id}/report")
    assert report.status_code == 200, report.text
    value = report.json()
    assert len(value["report"]["findings"]) >= expected
    if target == "101":
        assert not value["report"]["findings"]
    assert "分析建议" in value["markdown"] and "\r\n" in value["markdown"]
    with Session(context.engine) as session:
        run = session.get(RunRecord, run_id)
        trace = session.get(ArtifactRecord, UUID(run.result["trace_artifact_id"]))
        content = context.store.read_text(trace.storage_key, trace.sha256)
        assert "api_key" not in content.lower()
        assert len(json.loads(content)["calls"]) == run.result["model_calls"]
        assert run.configuration["code_sha256"] and run.configuration["system_prompt"]
    events = context.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    assert events[-1]["event_type"] == "run.succeeded"
    assert any(item["event_type"] == "model.completed" for item in events)


def test_auth_failure_finishes_once_with_trace_and_no_report(context):
    model = ScriptedModel([ModelError("model_auth_error", "密钥无效")])
    run_id, worker = agent_run(context, model_factory=lambda _: model)
    assert context.client.get(f"/api/v1/runs/{run_id}/report").status_code == 409
    assert worker.run_once()
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "failed" and result["error_code"] == "model_auth_error"
    assert len(model.calls) == 1
    assert context.client.get(f"/api/v1/runs/{run_id}/report").status_code == 409
    events = context.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    assert any(item["event_type"] == "analysis.trace_saved" for item in events)


def test_cancel_after_model_response_never_executes_requested_tool(context):
    from devflow.model_gateway import tool_call
    from devflow.workflows import cancel_run

    class CancellingModel:
        provider, name = "fake", "cancel-test"

        def complete(self, *args, **kwargs):
            with Session(context.engine) as session:
                cancel_run(session, run_id)
            return tool_call("get_pr", {"repo_id": "repo-taskboard"})

    run_id, worker = agent_run(context, model_factory=lambda _: CancellingModel())
    assert worker.run_once()
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "cancelled" and result["result"] is None
    events = context.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    assert not any(item["payload"].get("tool") == "get_pr" for item in events)
    assert any(item["event_type"] == "analysis.trace_saved" for item in events)


def test_task_timeout_keeps_last_model_trace_and_usage(context):
    from datetime import timedelta

    from devflow.model_gateway import ModelReply, Usage, tool_call
    from sqlalchemy import func, select

    class ExpiringModel:
        provider, name = "fake", "timeout-test"

        def complete(self, *args, **kwargs):
            with Session(context.engine) as session, session.begin():
                run = session.get(RunRecord, run_id)
                run.started_at = session.scalar(select(func.clock_timestamp())) - timedelta(
                    seconds=run.configuration["budget"]["timeout_seconds"] + 1,
                )
            return ModelReply(
                tool_call("get_pr", {"repo_id": "repo-taskboard"}).message,
                Usage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            )

    run_id, worker = agent_run(context, model_factory=lambda _: ExpiringModel())
    assert worker.run_once()
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "failed" and result["error_code"] == "timeout"
    assert result["result"] is None
    events = context.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    trace_event = next(item for item in events if item["event_type"] == "analysis.trace_saved")
    assert trace_event["payload"]["total_tokens"] == 5
    assert not any(item["payload"].get("tool") == "get_pr" for item in events)


def test_worker_subtracts_evidence_time_from_model_timeout(context):
    from datetime import timedelta

    from devflow.fake_model import FixtureModel
    from sqlalchemy import func, select

    class RecordingModel(FixtureModel):
        timeouts = []

        def complete(self, *args, **kwargs):
            self.timeouts.append(kwargs["timeout"])
            return super().complete(*args, **kwargs)

    model = RecordingModel()
    run_id, worker = agent_run(context, model_factory=lambda _: model)
    claimed = worker.claim(run_id)
    assert claimed
    with Session(context.engine) as session, session.begin():
        run = session.get(RunRecord, run_id)
        run.started_at = session.scalar(select(func.clock_timestamp())) - timedelta(
            seconds=run.configuration["budget"]["timeout_seconds"] - 10,
        )
    worker.execute(*claimed)
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "succeeded", result
    assert model.timeouts and all(0 < timeout <= 10 for timeout in model.timeouts)


def test_directory_only_report_always_discloses_unread_evidence(context):
    from devflow.model_gateway import ModelReply, tool_call

    class DirectoryOnlyModel:
        provider, name = "fake", "directory-test"

        def complete(self, messages, tools, **kwargs):
            if not any(message["role"] == "tool" for message in messages):
                return tool_call("get_pr", {"repo_id": "repo-taskboard"})
            return ModelReply(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "task_type": "pr_review",
                            "summary": "未确认风险。",
                            "findings": [],
                            "verification_steps": ["补查正文。"],
                            "suggestions": [],
                            "unconfirmed": [],
                            "scope": ["目录。"],
                        }
                    ),
                }
            )

    run_id, worker = agent_run(context, model_factory=lambda _: DirectoryOnlyModel())
    assert worker.run_once()
    result = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert result["status"] == "succeeded", result
    assert any("未读取任何证据正文" in item for item in result["result"]["report"]["unconfirmed"])
    assert not result["result"]["report"]["findings"]
