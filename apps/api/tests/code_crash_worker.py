# 文件用途：代码补查事务与模型 checkpoint 之前的真实进程退出验收。
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from devflow.analysis.tool_gateway import FileArgs
from devflow.code import tasks
from devflow.code.mcp_client import CodeMCPClient
from devflow.core.config import get_settings
from devflow.storage.artifact_store import ArtifactStore
from devflow.storage.database import create_database_engine
from devflow.workflows.worker import Worker


def main():
    database, root, run_id, token, commit, point = sys.argv[1:]
    assert database.startswith("devflow_test_") and len(database) == 45
    settings = get_settings().model_copy(update={"postgres_db": database, "model_provider": "fake"})
    engine = create_database_engine(settings)
    worker = Worker(engine, settings, store=ArtifactStore(Path(root)))
    if point == "before_commit":
        tasks.load_evidence = lambda *_: os._exit(73)
    args = FileArgs.model_validate_json(
        json.dumps(
            {
                "repo_id": "repo-taskboard",
                "commit": commit,
                "path": "taskboard/settings.py",
                "start_line": 1,
                "limit": 4,
            }
        )
    )
    client = CodeMCPClient(worker, UUID(run_id), UUID(token))
    client.start()
    assert client.info["status"] == "connected", client.info
    Path(root).parent.joinpath("crash-mcp-pid.txt").write_bytes(str(client.info["pid"]).encode())
    tasks.operation(worker, UUID(run_id), UUID(token), "read_file", args, mcp_client=client)
    # 已提交工具结果，但尚未返回给模型图或保存 checkpoint。
    os._exit(74)


if __name__ == "__main__":
    main()
