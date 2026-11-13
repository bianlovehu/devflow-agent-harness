# 文件用途：提供仓库知识库上传、版本预览、删除、检索调试和模型就绪状态接口。
import base64
import binascii
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select

from devflow.contracts import Contract
from devflow.embeddings import MODEL_DIR, MODEL_FILES, MODEL_KEY, get_embedder
from devflow.errors import DomainError
from devflow.knowledge import delete_document, search_knowledge, upload_document
from devflow.models import KnowledgeDocument, KnowledgeVersion
from devflow.workflow_api import Configuration, Database, Page, Store, page
from devflow.workflow_contracts import RecordResponse, RepoId
from devflow.workflows import require_repository

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def embedding_factory():
    # 只有实际索引/非空检索时加载模型；列表和空库问答可以完全离线打开。
    return get_embedder


EmbedderFactory = Annotated[object, Depends(embedding_factory)]


class KnowledgeUpload(Contract):
    repo_id: RepoId
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(max_length=6990508)


class KnowledgeSearch(Contract):
    repo_id: RepoId
    query: str = Field(min_length=1, max_length=500, pattern=r"\S")
    mode: Literal["hybrid", "keyword"] = "hybrid"
    limit: int = Field(default=6, ge=1, le=6)


class KnowledgeVersionOutput(RecordResponse):
    id: UUID
    number: int
    raw_sha256: str
    size_bytes: int
    status: Literal["indexing", "ready", "failed"]
    error_code: str | None
    error_message: str | None
    is_current: bool
    model_key: str | None
    chunk_count: int
    evidence_id: UUID | None
    created_at: datetime


class KnowledgeDocumentOutput(RecordResponse):
    id: UUID
    repo_id: str
    filename: str
    source: str
    deleted: bool
    created_at: datetime


class KnowledgeDetail(Contract):
    document: KnowledgeDocumentOutput
    versions: list[KnowledgeVersionOutput]


class KnowledgeUploadOutput(Contract):
    document_id: UUID
    version: KnowledgeVersionOutput
    duplicate: bool


class KnowledgePreview(Contract):
    version: KnowledgeVersionOutput
    content: str | None
    page_starts: list[dict]


class KnowledgeSearchHit(Contract):
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    version_number: int
    filename: str
    source: str
    evidence_id: UUID
    start_line: int
    end_line: int
    content: str
    token_count: int
    page: int | None
    ranks: dict[str, int]
    vector_similarity: float | None
    rrf_score: float


class KnowledgeSearchOutput(Contract):
    items: list[KnowledgeSearchHit]
    mode: Literal["hybrid", "keyword"]
    model_key: str
    note: str


def require_document(session, settings, repo_id, document_id):
    require_repository(session, repo_id)
    document = session.get(KnowledgeDocument, document_id)
    if document is None or document.repo_id != repo_id:
        raise DomainError(404, "document_not_found", "此仓库不存在该文档")
    return document


@router.get("/status")
def status():
    return {
        "model_files_ready": all((MODEL_DIR / name).is_file() for name in MODEL_FILES),
        "model_key": MODEL_KEY,
        "dimensions": 384,
        "chunk_tokens": 384,
        "overlap_tokens": 48,
        "max_upload_bytes": 5 * 1024 * 1024,
    }


@router.get("", response_model=Page[KnowledgeDocumentOutput])
def documents(
    repo_id: RepoId,
    session: Database,
    settings: Configuration,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_repository(session, repo_id)
    return page(
        session,
        select(KnowledgeDocument)
        .where(KnowledgeDocument.repo_id == repo_id, KnowledgeDocument.deleted.is_(False))
        .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id),
        limit,
        offset,
    )


@router.post("/upload", response_model=KnowledgeUploadOutput)
def upload(
    data: KnowledgeUpload,
    session: Database,
    settings: Configuration,
    store: Store,
    factory: EmbedderFactory,
):
    try:
        raw = base64.b64decode(data.content_base64, validate=True)
    except (ValueError, binascii.Error):
        raise DomainError(422, "document_base64", "文件内容编码无效") from None
    doc_id, version_id, duplicate = upload_document(
        session, settings, store, data.repo_id, data.filename, raw, embedder_factory=factory
    )
    return {
        "document_id": doc_id,
        "version": session.get(KnowledgeVersion, version_id),
        "duplicate": duplicate,
    }


@router.post("/search", response_model=KnowledgeSearchOutput)
def search(
    data: KnowledgeSearch, session: Database, settings: Configuration, factory: EmbedderFactory
):
    require_repository(session, data.repo_id)
    return search_knowledge(
        session,
        data.repo_id,
        data.query,
        mode=data.mode,
        limit=data.limit,
        embedder_factory=factory,
    )


@router.get("/{document_id}", response_model=KnowledgeDetail)
def detail(document_id: UUID, repo_id: RepoId, session: Database, settings: Configuration):
    document = require_document(session, settings, repo_id, document_id)
    versions = session.scalars(
        select(KnowledgeVersion)
        .where(KnowledgeVersion.document_id == document_id)
        .order_by(KnowledgeVersion.number.desc())
        .limit(100)
    ).all()
    return {"document": document, "versions": versions}


@router.get("/{document_id}/versions/{version_id}", response_model=KnowledgePreview)
def preview(
    document_id: UUID, version_id: UUID, repo_id: RepoId, session: Database, settings: Configuration
):
    require_document(session, settings, repo_id, document_id)
    version = session.get(KnowledgeVersion, version_id)
    if version is None or version.document_id != document_id:
        raise DomainError(404, "document_version_not_found", "文档版本不存在")
    return {"version": version, "content": version.content, "page_starts": version.page_starts}


@router.post("/{document_id}/delete")
def remove(document_id: UUID, repo_id: RepoId, session: Database, settings: Configuration):
    with session.begin():
        document = require_document(session, settings, repo_id, document_id)
        delete_document(session, document)
    return {"deleted": True, "document_id": document_id}
