# 文件用途：在复核请求发出前后强制退出真实worker，验证恢复不重复发送复核。
import os
import sys
from pathlib import Path
from uuid import UUID

from devflow.artifact_store import ArtifactStore
from devflow.config import get_settings
from devflow.database import create_database_engine
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

    class CrashWorker(Worker):
        def _journal_write(self, run_id, token, key, value):
            super()._journal_write(run_id, token, key, value)
            if key != "runtime" or not value.get("trace", {}).get("calls"):
                return
            last = value["trace"]["calls"][-1]
            if last.get("phase") == "review" and bool("response" in last) == (point == "reply"):
                os._exit(73)

    engine = create_database_engine(settings)
    worker = CrashWorker(engine, settings, ArtifactStore(Path(root)))
    claimed = worker.claim(UUID(run_id))
    assert claimed
    worker.execute(*claimed)
    raise AssertionError("复核中断点未到达")


if __name__ == "__main__":
    main()
