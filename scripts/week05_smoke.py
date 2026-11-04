# 文件用途：在临时数据库验收记忆提取、人工审核和新会话召回，可显式调用真实模型。
import argparse
import json
import tempfile
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from devflow.artifact_store import ArtifactStore, get_artifact_store
from devflow.config import PROJECT_ROOT, get_settings
from devflow.data_source import fixture_source
from devflow.database import create_database_engine, get_session
from devflow.import_fixtures import import_dataset
from devflow.main import app
from devflow.memory import recall_memories
from devflow.worker import Worker
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="显式使用 .env 中的真实供应商提取经验")
    args = parser.parse_args()
    configured = get_settings()
    if args.real and configured.model_provider == "fake":
        raise SystemExit("--real 需要先在服务端配置真实模型供应商")
    database = "devflow_test_" + uuid.uuid4().hex
    settings = configured.model_copy(
        update={
            "postgres_db": database,
            "data_source": "fixture",
            "fixture_storage": "database",
            "analysis_executor": "agent",
            "simulation_step_seconds": 0,
            "model_provider": configured.model_provider if args.real else "fake",
            "model_max_output_tokens": 2000,
            "context_input_tokens": 12000,
        }
    )
    admin = create_database_engine(configured).execution_options(isolation_level="AUTOCOMMIT")
    engine, created = None, False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        created = True
        engine = create_database_engine(settings)
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.check(config)
        with tempfile.TemporaryDirectory(prefix="devflow-week05-") as directory:
            store = ArtifactStore(Path(directory))
            with Session(engine, expire_on_commit=False) as session:
                import_dataset(session, fixture_source().dataset, store)

            def sessions():
                with Session(engine, expire_on_commit=False) as session:
                    yield session

            app.dependency_overrides[get_session] = sessions
            app.dependency_overrides[get_settings] = lambda: settings
            app.dependency_overrides[get_artifact_store] = lambda: store
            with TestClient(app) as client:

                def checked(response):
                    if response.status_code >= 400:
                        raise RuntimeError(response.text)
                    return response.json()

                conversation = checked(
                    client.post(
                        "/api/v1/conversations",
                        json={"repo_id": "repo-taskboard", "title": "第五周记忆审核验收"},
                    )
                )
                run = checked(
                    client.post(
                        "/api/v1/runs",
                        json={
                            "repo_id": "repo-taskboard",
                            "conversation_id": conversation["id"],
                            "task_type": "pr_review",
                            "target_id": "102",
                            "use_knowledge": False,
                            "question": "请核查任务列表 PR 的所有者隔离回归，并引用固定证据。",
                        },
                    )
                )
                worker = Worker(engine, settings, store)
                worker.execute(*worker.claim(uuid.UUID(run["id"])))
                run = checked(client.get(f"/api/v1/runs/{run['id']}"))
                if run["status"] != "succeeded":
                    raise RuntimeError(f"分析失败：{run['error_code']} {run['error_message']}")
                report = checked(client.get(f"/api/v1/runs/{run['id']}/report"))
                if not report["report"]["findings"]:
                    raise RuntimeError("模型未返回带证据的发现项，无法提取经验")
                candidate = checked(
                    client.post(f"/api/v1/runs/{run['id']}/memories", json={"finding_index": 0})
                )
                version = candidate["applicable_version"]
                with Session(engine) as session:
                    assert not recall_memories(session, run["repo_id"], version)
                checked(
                    client.post(
                        f"/api/v1/memories/{candidate['id']}/approve?repo_id={run['repo_id']}",
                        json={},
                    )
                )
                engine.dispose()
                with Session(engine) as session:
                    assert recall_memories(session, run["repo_id"], version)
                    assert not recall_memories(session, run["repo_id"], "f" * 40)
                new_conversation = checked(
                    client.post(
                        "/api/v1/conversations",
                        json={"repo_id": "repo-taskboard", "title": "新会话召回验证"},
                    )
                )
                # 第二轮使用明确标注的假模型，只验证新会话组装，不增加真实模型费用。
                settings = settings.model_copy(update={"model_provider": "fake"})
                followup = checked(
                    client.post(
                        "/api/v1/runs",
                        json={
                            "repo_id": "repo-taskboard",
                            "conversation_id": new_conversation["id"],
                            "task_type": "pr_review",
                            "target_id": "102",
                            "use_knowledge": False,
                            "question": "继续核查所有者隔离",
                        },
                    )
                )
                worker = Worker(engine, settings, store)
                worker.execute(*worker.claim(uuid.UUID(followup["id"])))
                followup = checked(client.get(f"/api/v1/runs/{followup['id']}"))
                assert candidate["id"] in followup["result"]["recalled_memories"]
                checked(
                    client.post(
                        f"/api/v1/memories/{candidate['id']}/revoke?repo_id={run['repo_id']}",
                        json={},
                    )
                )
                with Session(engine) as session:
                    assert not recall_memories(session, run["repo_id"], version)
                summary = {
                    "data_source": "fixture",
                    "provider": run["result"]["provider"],
                    "model": run["result"]["model"],
                    "usage": run["result"]["usage"],
                    "context": run["result"]["context"],
                    "extraction": candidate["extraction"],
                    "memory_summary": candidate["summary"],
                    "followup_provider": "fake",
                    "checks": [
                        "pending_excluded",
                        "approval",
                        "fresh_session_recall",
                        "database_reconnect",
                        "version_mismatch_excluded",
                        "revoke",
                    ],
                }
                target = (
                    PROJECT_ROOT
                    / "data"
                    / ("week05-real-proof.json" if args.real else "week05-proof.json")
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\r\n",
                )
                target.with_suffix(".md").write_text(
                    report["markdown"].replace("\r\n", "\n"), encoding="utf-8", newline="\r\n"
                )
                print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        app.dependency_overrides.clear()
        if engine:
            engine.dispose()
        if created:
            assert database.startswith("devflow_test_") and len(database) == 45
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
