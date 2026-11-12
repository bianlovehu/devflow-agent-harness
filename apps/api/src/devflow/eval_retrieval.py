# 文件用途：在专用PostgreSQL/pgvector库导入固定文档，评测真实关键词/混合召回并提供Agent工具。
import hashlib
import re
import time
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from devflow.artifact_store import ArtifactStore
from devflow.bootstrap import migrate
from devflow.data_source import fixture_source
from devflow.database import create_database_engine
from devflow.embeddings import MODEL_KEY, get_embedder
from devflow.evaluation import digest
from devflow.import_fixtures import import_dataset
from devflow.knowledge import search_knowledge, upload_document
from devflow.models import ArtifactRecord, EvidenceRecord, KnowledgeVersion


class ProductionRetrieval:
    def __init__(self, settings, cases, directory):
        self.settings = settings.model_copy(
            update={
                "postgres_db": "devflow_eval_" + uuid.uuid4().hex,
                "data_source": "fixture",
                "fixture_storage": "database",
            }
        )
        self.admin = create_database_engine(settings).execution_options(
            isolation_level="AUTOCOMMIT"
        )
        self.engine = None
        self.created = False
        self.store = ArtifactStore(directory)
        self.documents = []
        self.cases, self.queries = cases, []

    def __enter__(self):
        try:
            with self.admin.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{self.settings.postgres_db}"'))
            self.created = True
            self.engine = create_database_engine(self.settings)
            migrate(self.engine)
            with Session(self.engine, expire_on_commit=False) as session:
                import_dataset(session, fixture_source().dataset, self.store)
            # 共用一个语料库，两个检索模式使用同一批文档版本和向量，绝不按答案过滤检索范围。
            corpus = [
                (c.case_id, s.key, s.content)
                for c in self.cases
                for s in c.sources
                if s.source_type == "document"
            ]
            corpus += [
                (
                    "distractor-" + str(i),
                    "background",
                    f"一般运维记录 {i}：演示接口只读，部署版本和负责人尚未登记。",
                )
                for i in range(8)
            ]
            for case_id, key, content in corpus:
                with Session(self.engine, expire_on_commit=False) as session:
                    _, version_id, _ = upload_document(
                        session,
                        self.settings,
                        self.store,
                        "repo-taskboard",
                        f"{case_id}-{key}.md",
                        content.encode(),
                        source="eval-fixed-corpus",
                        embedder_factory=get_embedder,
                    )
                    version = session.get(KnowledgeVersion, version_id)
                    if version.status != "ready":
                        raise RuntimeError("生产评测文档索引失败")
                    self.documents.append(
                        {
                            "case_id": case_id,
                            "source_key": key,
                            "version_id": str(version_id),
                            "evidence_id": str(version.evidence_id),
                            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                        }
                    )
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    @property
    def manifest(self):
        return {
            "database": self.settings.postgres_db,
            "model_key": MODEL_KEY,
            "documents": self.documents,
            "corpus_sha256": digest(
                [
                    {k: d[k] for k in ["case_id", "source_key", "content_sha256"]}
                    for d in self.documents
                ]
            ),
        }

    def retrieve(self, query, mode):
        started = time.monotonic()
        with Session(self.engine) as session:
            found = search_knowledge(
                session,
                "repo-taskboard",
                query,
                mode=mode,
                limit=6,
                version_ids=[d["version_id"] for d in self.documents],
            )
        self.queries.append(
            {
                "query": query,
                "mode": mode,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "result": found,
            }
        )
        return found

    def tool(self, case, mode):
        def search(query):
            found = self.retrieve(query, mode)
            returned = []
            by_evidence = {d["evidence_id"]: d for d in self.documents}
            with Session(self.engine) as session:
                for hit in found["items"]:
                    evidence = session.get(EvidenceRecord, uuid.UUID(hit["evidence_id"]))
                    artifact = session.get(ArtifactRecord, evidence.artifact_id)
                    meta = by_evidence[str(evidence.id)]
                    returned.append(
                        {
                            "id": str(evidence.id),
                            "artifact_id": str(artifact.id),
                            "source_type": "document",
                            "path": evidence.path,
                            "version": evidence.version,
                            "start_line": evidence.start_line,
                            "end_line": evidence.end_line,
                            "source_key": meta["source_key"]
                            if meta["case_id"] == case.case_id
                            else meta["case_id"] + ":" + meta["source_key"],
                            "content_sha256": artifact.sha256,
                            "content": self.store.read_text(artifact.storage_key, artifact.sha256),
                        }
                    )
                    hit["id"] = str(evidence.id)
                    hit["lines"] = [
                        {"line": hit["start_line"] + i, "text": line}
                        for i, line in enumerate(hit.pop("content").splitlines())
                    ]
            found["_evidence"] = returned
            return found

        return search

    def evaluate(self, cases):
        rows = []
        for case in cases:
            if case.task_type != "knowledge_qa":
                continue
            relevant = {d["version_id"] for d in self.documents if d["case_id"] == case.case_id}
            for mode in ["keyword", "hybrid"]:
                found = self.retrieve(case.question, mode)
                selected = {h["version_id"] for h in found["items"]}
                rows.append(
                    {
                        "case_id": case.case_id,
                        "mode": mode,
                        "relevant_version_ids": sorted(relevant),
                        "retrieved_version_ids": sorted(selected),
                        "recall_at_6": len(relevant & selected) / len(relevant)
                        if relevant
                        else None,
                        "no_relevant_documents": not relevant,
                        "hits": found["items"],
                        "duration_ms": self.queries[-1]["duration_ms"],
                    }
                )
        return rows

    def __exit__(self, *args):
        if self.engine is not None:
            self.engine.dispose()
        if self.created:
            assert re.fullmatch(r"devflow_eval_[0-9a-f]{32}", self.settings.postgres_db)
            with self.admin.connect() as connection:
                connection.execute(
                    text(f'DROP DATABASE "{self.settings.postgres_db}" WITH (FORCE)')
                )
            self.created = False
        self.admin.dispose()
