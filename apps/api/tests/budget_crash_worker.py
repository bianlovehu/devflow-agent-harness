# 文件用途：在隔离 worker 的 HTTP 调用边界强制退出，验证主账本预留不丢失。
import os
import sys
from pathlib import Path
from uuid import UUID

from devflow.artifact_store import ArtifactStore
from devflow.budget import BudgetLedger
from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.model_gateway import DeepSeekModel
from devflow.worker import Worker
from pydantic import SecretStr


def main():
    database, artifact_root, run_id = sys.argv[1:]
    assert database.startswith("devflow_test_") and len(database) == 45
    settings = get_settings().model_copy(
        update={
            "postgres_db": database,
            "data_source": "fixture",
            "model_provider": "aliyun",
            "analysis_executor": "agent",
            "simulation_step_seconds": 0,
            "dashscope_api_key": SecretStr("private"),
            "dashscope_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        }
    )
    engine = create_database_engine(settings)

    class ExitBeforeNetwork:
        def open(self, *args, **kwargs):
            os._exit(73)

    worker = Worker(
        engine,
        settings,
        ArtifactStore(Path(artifact_root)),
        model_factory=lambda s: DeepSeekModel(
            s,
            ledger=BudgetLedger(engine, settings),
            opener=ExitBeforeNetwork(),
            purpose="analysis",
            run_id=UUID(run_id),
            source="crash_test",
        ),
    )
    worker.execute(*worker.claim(UUID(run_id)))
    raise AssertionError("expected crash was not reached")


if __name__ == "__main__":
    main()
