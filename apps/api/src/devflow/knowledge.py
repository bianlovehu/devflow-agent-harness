# 文件用途：文档解析、版本切换、token 分块、向量缓存和限定仓库的 RRF 混合检索。
import hashlib
import io
import re
import uuid
from bisect import bisect_right
from datetime import UTC, datetime
from pathlib import PurePath

import jieba
from pypdf import PdfReader
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from devflow.embeddings import MODEL_KEY, get_embedder
from devflow.errors import DomainError
from devflow.import_fixtures import json_digest
from devflow.models import (
    ArtifactRecord,
    EmbeddingCache,
    EvidenceRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    ResourceSnapshot,
)
from devflow.workflows import require_repository

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CHUNK_TOKENS = 384
CHUNK_OVERLAP = 48
_segmenter = jieba.Tokenizer()


def lexical_terms(text):
    # 文档和查询共用规则：中文分词、英文 snake/camel 标识符及其组成词。
    words = []
    for value in re.findall(r"[\u3400-\u9fff]+|[a-zA-Z0-9_]+", text):
        if re.search(r"[\u3400-\u9fff]", value):
            words.extend(w for w in _segmenter.cut(value) if w.strip())
        else:
            words.append(value.lower())
            words.extend(re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).lower().split("_"))
    return sorted({word for item in words for word in item.split() if word})


def parse_document(filename, raw):
    suffix = PurePath(filename).suffix.lower()
    pages = []
    if suffix in {".md", ".txt"}:
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise DomainError(422, "document_encoding", "Markdown/TXT 需要 UTF-8 编码") from None
        if "\x00" in content:
            raise DomainError(422, "document_binary", "文档包含二进制内容")
    elif suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise DomainError(422, "pdf_encrypted", "暂不支持加密 PDF")
            if len(reader.pages) > 50:
                raise DomainError(413, "pdf_page_limit", "PDF 最多 50 页")
            parts, line = [], 1
            for number, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n")
                if not text.strip():
                    raise DomainError(
                        422, "pdf_ocr_required", "PDF 含无可提取文本的页面，暂不支持扫描件/OCR"
                    )
                text = text.rstrip("\n")
                parts.append(text)
                pages.append({"page": number, "start_line": line})
                line += text.count("\n") + 2
                if sum(len(t) for t in parts) > 1000000:
                    raise DomainError(413, "document_text_limit", "提取文本超过 100 万字符")
            content = "\n\n".join(parts)
        except DomainError:
            raise
        except Exception:
            raise DomainError(422, "pdf_parse_failed", "PDF 无法解析或已损坏") from None
    else:
        raise DomainError(415, "document_type", "仅支持 Markdown、TXT 和文本 PDF")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.strip():
        raise DomainError(422, "document_empty", "文档没有可检索文本")
    if len(content) > 1000000:
        raise DomainError(413, "document_text_limit", "提取文本超过 100 万字符")
    return content, pages


def split_chunks(content, tokenizer):
    # 优先在标题/段落边界切分；长段落再按真实 tokenizer offset 滑窗，保持原文行号。
    offsets = tokenizer.encode(content, add_special_tokens=False).offsets
    starts = [pair[0] for pair in offsets]
    boundaries = sorted(
        {bisect_right(starts, m.end() - 1) for m in re.finditer(r"\n\s*\n|\n(?=#{1,6} )", content)}
    )
    spans, start = [], 0
    while start < len(offsets):
        end = min(start + CHUNK_TOKENS, len(offsets))
        if end < len(offsets):
            preferred = [b for b in boundaries if start + CHUNK_TOKENS // 2 <= b <= end]
            if preferred:
                end = preferred[-1]
        # SentencePiece 在片段开头可能新增词边界 token；offset 窗口需再次核对实际块长。
        while (
            end > start + 1
            and len(
                tokenizer.encode(
                    content[offsets[start][0] : offsets[end - 1][1]], add_special_tokens=False
                ).ids
            )
            > CHUNK_TOKENS
        ):
            end -= 1
        spans.append((offsets[start][0], offsets[end - 1][1]))
        if end == len(offsets):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    chunks = []
    for begin, end in spans:
        text = content[begin:end]
        if not text.strip():
            continue
        chunks.append(
            {
                "content": text,
                "start_line": content.count("\n", 0, begin) + 1,
                "end_line": content.count("\n", 0, end - 1) + 1,
                "token_count": len(tokenizer.encode(text, add_special_tokens=False).ids),
            }
        )
    if len(chunks) > 512:
        raise DomainError(413, "document_chunk_limit", "文档超过 512 个块，请拆成多个文件")
    return chunks


def repository_lock(session, repo_id):
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(repo_id, 73))))


def active_versions(session, repo_id):
    return session.scalars(
        select(KnowledgeVersion.id)
        .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeVersion.repo_id == repo_id,
            KnowledgeVersion.is_current.is_(True),
            KnowledgeVersion.status == "ready",
            KnowledgeDocument.deleted.is_(False),
        )
        .order_by(KnowledgeVersion.id)
    ).all()


def upload_document(
    session,
    settings,
    store,
    repo_id,
    filename,
    raw,
    *,
    source="upload",
    embedder_factory=get_embedder,
):
    if settings.data_source == "fixture" and settings.fixture_storage != "database":
        raise DomainError(503, "persistent_storage_required", "知识库导入需要数据库存储模式")
    if (
        not filename
        or len(filename) > 200
        or re.search(r"[\\/\x00-\x1f]", filename)
        or filename in {".", ".."}
    ):
        raise DomainError(422, "document_filename", "请使用不含目录的文件名，最长 200 字符")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise DomainError(413, "document_size", "单文件最大 5 MiB")
    digest = hashlib.sha256(raw).hexdigest()
    with session.begin():
        require_repository(session, repo_id, settings.data_source)
        repository_lock(session, repo_id)
        document = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.repo_id == repo_id, KnowledgeDocument.filename == filename
            )
        )
        duplicate = session.scalar(
            select(KnowledgeVersion)
            .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeVersion.repo_id == repo_id,
                KnowledgeVersion.raw_sha256 == digest,
                KnowledgeVersion.model_key == MODEL_KEY,
                KnowledgeVersion.is_current.is_(True),
                KnowledgeDocument.deleted.is_(False),
            )
        )
        if duplicate:
            if document is not None and document.id != duplicate.document_id:
                # 更新为库中已有内容时合并到有效文档，不能继续召回被替换的旧正文。
                delete_document(session, document)
            return duplicate.document_id, duplicate.id, True
        if document is None:
            document = KnowledgeDocument(repo_id=repo_id, filename=filename, source=source)
            session.add(document)
            session.flush()
        document.deleted = False
        number = (
            session.scalar(
                select(func.max(KnowledgeVersion.number)).where(
                    KnowledgeVersion.document_id == document.id
                )
            )
            or 0
        ) + 1
        key, _, size = store.put_bytes(raw)
        version = KnowledgeVersion(
            document_id=document.id,
            repo_id=repo_id,
            number=number,
            raw_sha256=digest,
            raw_storage_key=key,
            size_bytes=size,
            status="indexing",
        )
        session.add(version)
        session.flush()
        document_id, version_id = document.id, version.id
    try:
        content, pages = parse_document(filename, raw)
        embedder = embedder_factory()
        chunks = split_chunks(content, embedder.tokenizer)
        vectors = []
        # 缓存键覆盖模型、前缀/池化配置和块内容，不会把旧模型向量用于新模型。
        with session.begin():
            for chunk in chunks:
                sha = hashlib.sha256(chunk["content"].encode()).hexdigest()
                cached = session.get(EmbeddingCache, (embedder.key, sha))
                vectors.append(list(cached.embedding) if cached is not None else None)
        missing = [i for i, value in enumerate(vectors) if value is None]
        for index, vector in zip(
            missing, embedder.encode([chunks[i]["content"] for i in missing]), strict=True
        ):
            vectors[index] = vector
        with session.begin():
            repository_lock(session, repo_id)
            document = session.get(KnowledgeDocument, document_id, populate_existing=True)
            version = session.get(KnowledgeVersion, version_id, populate_existing=True)
            version.content, version.page_starts, version.model_key = content, pages, embedder.key
            newer = session.scalar(
                select(KnowledgeVersion.id).where(
                    KnowledgeVersion.document_id == document_id,
                    KnowledgeVersion.is_current.is_(True),
                    KnowledgeVersion.number > version.number,
                )
            )
            if document.deleted or newer:
                version.status = "failed"
                version.error_code, version.error_message = (
                    "document_superseded",
                    "索引期间文档已删除或被新版本替换，请重新上传",
                )
                return document_id, version_id, False
            previous = session.scalars(
                select(KnowledgeVersion.id).where(KnowledgeVersion.document_id == document_id)
            ).all()
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.version_id.in_(previous)))
            session.execute(
                update(KnowledgeVersion)
                .where(KnowledgeVersion.document_id == document_id)
                .values(is_current=False)
            )
            session.flush()
            payload = {
                "document_id": str(document_id),
                "version": str(version_id),
                "filename": filename,
                "source": source,
                "raw_sha256": digest,
            }
            session.execute(
                update(ResourceSnapshot)
                .where(
                    ResourceSnapshot.repo_id == repo_id,
                    ResourceSnapshot.kind == "document",
                    ResourceSnapshot.external_id == "kb-" + str(document_id),
                )
                .values(is_current=False)
            )
            snapshot = ResourceSnapshot(
                repo_id=repo_id,
                kind="document",
                external_id="kb-" + str(document_id),
                content_sha256=json_digest(payload),
                payload=payload,
                is_current=True,
            )
            session.add(snapshot)
            session.flush()
            key, sha, size = store.put_text(content)
            artifact = session.scalar(
                select(ArtifactRecord).where(
                    ArtifactRecord.repo_id == repo_id, ArtifactRecord.sha256 == sha
                )
            )
            if artifact is None:
                artifact = ArtifactRecord(
                    repo_id=repo_id,
                    sha256=sha,
                    size_bytes=size,
                    media_type="text/plain; charset=utf-8",
                    storage_key=key,
                )
                session.add(artifact)
                session.flush()
            evidence = EvidenceRecord(
                repo_id=repo_id,
                resource_snapshot_id=snapshot.id,
                artifact_id=artifact.id,
                source_type="document",
                path="knowledge/" + filename,
                version=str(version_id),
                start_line=1,
                end_line=len(content.split("\n")),
                retrieved_at=datetime.now(UTC),
            )
            session.add(evidence)
            session.flush()
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                sha = hashlib.sha256(chunk["content"].encode()).hexdigest()
                session.execute(
                    insert(EmbeddingCache)
                    .values(model_key=embedder.key, content_sha256=sha, embedding=vector)
                    .on_conflict_do_nothing()
                )
                session.add(
                    KnowledgeChunk(
                        repo_id=repo_id,
                        version_id=version_id,
                        ordinal=index,
                        **chunk,
                        embedding=vector,
                        keywords=func.to_tsvector(
                            "simple", " ".join(lexical_terms(chunk["content"]))
                        ),
                    )
                )
            version.evidence_id, version.chunk_count = evidence.id, len(chunks)
            version.status, version.is_current = "ready", True
            document.source = source
    except DomainError as error:
        session.rollback()
        with session.begin():
            version = session.get(KnowledgeVersion, version_id)
            version.status, version.error_code, version.error_message = (
                "failed",
                error.code,
                error.message,
            )
    except Exception:
        session.rollback()
        with session.begin():
            version = session.get(KnowledgeVersion, version_id)
            version.status, version.error_code, version.error_message = (
                "failed",
                "index_failed",
                "文档索引失败，请检查本地模型并重新上传",
            )
    return document_id, version_id, False


def delete_document(session, document):
    repository_lock(session, document.repo_id)
    document.deleted = True
    versions = select(KnowledgeVersion.id).where(KnowledgeVersion.document_id == document.id)
    session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.version_id.in_(versions)))
    session.execute(
        update(KnowledgeVersion)
        .where(KnowledgeVersion.document_id == document.id)
        .values(is_current=False)
    )
    session.execute(
        update(ResourceSnapshot)
        .where(
            ResourceSnapshot.repo_id == document.repo_id,
            ResourceSnapshot.external_id == "kb-" + str(document.id),
            ResourceSnapshot.kind == "document",
        )
        .values(is_current=False)
    )


def search_knowledge(
    session,
    repo_id,
    query,
    *,
    version_ids=None,
    mode="hybrid",
    limit=6,
    embedder_factory=get_embedder,
):
    base = (
        select(KnowledgeChunk, KnowledgeVersion, KnowledgeDocument)
        .join(KnowledgeVersion, KnowledgeChunk.version_id == KnowledgeVersion.id)
        .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeChunk.repo_id == repo_id,
            KnowledgeVersion.is_current.is_(True),
            KnowledgeVersion.status == "ready",
            KnowledgeDocument.deleted.is_(False),
            KnowledgeVersion.model_key == MODEL_KEY,
        )
    )
    if version_ids is not None:
        base = base.where(KnowledgeVersion.id.in_([uuid.UUID(str(v)) for v in version_ids]))
    if not session.scalar(select(base.exists())):
        return {
            "items": [],
            "mode": mode,
            "model_key": MODEL_KEY,
            "note": "没有可用的有效文档版本，证据不足",
        }
    terms = lexical_terms(query)
    ranked, rows, scores = {}, {}, {}
    if terms:
        tsquery = func.to_tsquery("simple", " | ".join(terms[:80]))
        rank = func.ts_rank_cd(KnowledgeChunk.keywords, tsquery)
        for index, row in enumerate(
            session.execute(
                base.where(KnowledgeChunk.keywords.op("@@")(tsquery))
                .order_by(rank.desc(), KnowledgeChunk.id)
                .limit(20)
            ),
            1,
        ):
            key = str(row[0].id)
            rows[key], ranked[key] = row, {"keyword_rank": index}
    if mode == "hybrid":
        embedder = embedder_factory()
        vector = embedder.encode([query], query=True)[0]
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        for index, row in enumerate(
            session.execute(
                base.add_columns(distance).order_by(distance, KnowledgeChunk.id).limit(20)
            ),
            1,
        ):
            key = str(row[0].id)
            # E5 相似度偏高；阈值用于排除明显无关片段，仍由模型判断支持程度。
            similarity = 1 - float(row[3])
            if similarity < 0.75:
                continue
            rows[key] = row
            ranked.setdefault(key, {})["vector_rank"] = index
            scores[key] = round(similarity, 6)
    items = []
    for key, ranks in ranked.items():
        chunk, version, doc = rows[key][:3]
        items.append(
            {
                "chunk_id": key,
                "document_id": str(doc.id),
                "version_id": str(version.id),
                "version_number": version.number,
                "filename": doc.filename,
                "source": doc.source,
                "evidence_id": str(version.evidence_id),
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "page": next(
                    (
                        p["page"]
                        for p in reversed(version.page_starts)
                        if p["start_line"] <= chunk.start_line
                    ),
                    None,
                ),
                "ranks": ranks,
                "vector_similarity": scores.get(key),
                "rrf_score": sum(1 / (60 + rank) for rank in ranks.values()),
            }
        )
    items.sort(key=lambda item: (-item["rrf_score"], item["chunk_id"]))
    return {
        "items": items[:limit],
        "mode": mode,
        "model_key": MODEL_KEY,
        "note": "向量/关键词各召回前20，RRF(k=60)；资料是历史约束，不能代表当前代码或 CI 状态",
    }
