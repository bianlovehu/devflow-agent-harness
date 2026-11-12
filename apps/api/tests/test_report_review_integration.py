# 文件用途：在隔离PostgreSQL验证复核记录保存、报告绑定及进程恢复。
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
import test_persistence_integration as persistence
from devflow.config import PROJECT_ROOT
from devflow.models import RunRecord
from devflow.report_review import digest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_week03_integration import agent_run

context = persistence.context
pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1", reason="isolated PostgreSQL required"
)


def assert_bound(context, run_id):
    run = context.client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "succeeded", run
    response = context.client.get(f"/api/v1/runs/{run_id}/report")
    assert response.status_code == 200, response.text
    payload = response.json()
    record = payload["review"]
    assert record["output_report_sha256"] == digest(payload["report"])
    assert record["input_report_sha256"] == digest(record["initial_report"])
    assert record["review_calls"] == 1 and record["supplement_rounds"] == 0
    assert payload["report"]["semantic_support"]["status"] == "not_reviewed"
    assert "模型复核意见（辅助）" in payload["markdown"]
    return record


def test_real_worker_persists_review_and_binds_exported_report(context):
    run_id, worker = agent_run(context)
    assert worker.run_once()
    assert assert_bound(context, run_id)["status"] == "completed"


@pytest.mark.parametrize("point", ["request", "reply"])
def test_recovery_of_review_in_real_process_does_not_resend(context, point):
    run_id, worker = agent_run(context)
    child = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("report_review_crash_worker.py")),
            context.database_name,
            str(context.store.root),
            str(run_id),
            point,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        timeout=50,
    )
    assert child.returncode == 73, child.stderr.decode(errors="replace")
    with Session(context.engine) as session, session.begin():
        run = session.get(RunRecord, UUID(str(run_id)))
        run.lease_expires_at = session.scalar(select(func.clock_timestamp())) - timedelta(seconds=1)
    claimed = worker.claim(run_id)
    assert claimed
    worker.execute(*claimed)
    record = assert_bound(context, run_id)
    assert record["status"] == ("completed" if point == "reply" else "review_unavailable")
