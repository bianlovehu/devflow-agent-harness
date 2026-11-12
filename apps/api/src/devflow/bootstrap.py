# 文件用途：显式、串行执行迁移与幂等样例初始化；API和worker启动时不迁移。
import argparse
import json

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from devflow.artifact_store import ArtifactStore
from devflow.config import PROJECT_ROOT, get_settings
from devflow.data_source import fixture_source
from devflow.database import create_database_engine
from devflow.import_fixtures import import_dataset
from devflow.knowledge import upload_document
from devflow.models import KnowledgeVersion


def migrate(engine):
    # 会话级锁在事务提交后仍持有；并发显式初始化也只能有一个执行迁移。
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(529053173)"))
        connection.commit()
        try:
            config = Config(str(PROJECT_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
        finally:
            connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(529053173)"))
            connection.commit()


def initialize(settings, *, seed=False, knowledge=False):
    engine, store = create_database_engine(settings), ArtifactStore()
    try:
        migrate(engine)
        result = {"migrations": "head", "documents": []}
        if seed:
            with Session(engine, expire_on_commit=False) as session:
                result["fixtures"] = import_dataset(session, fixture_source().dataset, store)
        if knowledge:
            fixture_settings = settings.model_copy(update={"data_source": "fixture"})
            docs = [
                (d.repo_id, d.id + ".md", d.content.encode())
                for d in fixture_source().dataset.documents
            ]
            english = PROJECT_ROOT / "fixtures/knowledge/owner-policy.en.md"
            docs.append(("repo-taskboard", english.name, english.read_bytes()))
            for repo_id, filename, raw in docs:
                with Session(engine, expire_on_commit=False) as session:
                    doc_id, version_id, duplicate = upload_document(
                        session, fixture_settings, store, repo_id, filename, raw, source="fixture"
                    )
                    version = session.get(KnowledgeVersion, version_id)
                    if version.status != "ready":
                        raise RuntimeError("知识样例索引失败，请核对显式准备的模型文件")
                    result["documents"].append(
                        {"id": str(doc_id), "version": str(version_id), "duplicate": duplicate}
                    )
        return result
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="显式迁移和样例初始化")
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--knowledge", action="store_true")
    args = parser.parse_args()
    if args.knowledge and not args.seed:
        parser.error("--knowledge 需同时指定 --seed")
    print(
        json.dumps(
            initialize(get_settings(), seed=args.seed, knowledge=args.knowledge), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
