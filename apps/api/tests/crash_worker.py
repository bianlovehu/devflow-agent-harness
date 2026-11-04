# 文件用途：验收专用子进程，在真实 PostgreSQL worker 的三个持久化边界强制退出。
import os
import sys
from pathlib import Path
from uuid import UUID

from devflow.artifact_store import ArtifactStore
from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.fake_model import FixtureModel
from devflow.worker import Worker


def main():
    database, root, run_id, point = sys.argv[1:]
    assert database.startswith("devflow_test_")
    settings = get_settings().model_copy(
        update={
            "postgres_db": database,
            "model_provider": "fake",
            "data_source": "fixture",
            "simulation_step_seconds": 0,
        }
    )

    class CrashModel(FixtureModel):
        def complete(self, messages, tools, **kwargs):
            if point == "model_call" and any(m["role"] == "tool" for m in messages):
                os._exit(73)
            return super().complete(messages, tools, **kwargs)

    class CrashWorker(Worker):
        def _journal_write(self, run_id, token, key, value):
            super()._journal_write(run_id, token, key, value)
            if point == "after_tool" and key.startswith("tool:"):
                os._exit(73)

        def _finish(self, run_id, token, status, **kwargs):
            if point == "before_report" and status == "succeeded":
                os._exit(73)
            return super()._finish(run_id, token, status, **kwargs)

    engine = create_database_engine(settings)
    worker = CrashWorker(
        engine, settings, ArtifactStore(Path(root)), model_factory=lambda _: CrashModel()
    )
    claimed = worker.claim(UUID(run_id))
    assert claimed is not None
    worker.execute(*claimed)
    raise AssertionError("expected crash point was not reached")


if __name__ == "__main__":
    main()
