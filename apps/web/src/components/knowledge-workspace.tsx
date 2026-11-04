// 文件用途：维护仓库文档、查看索引/版本/原文、调试混合检索并创建知识问答。
"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { fetchData, postData } from "@/lib/api-client";
import type { Collection, Repository, RuntimeInfo } from "@/lib/repositories";
import type { Page } from "@/lib/workflows";
import type { components } from "@/lib/generated/api";
import { QueryState } from "@/components/query-state";
import { AnalysisForm } from "@/components/analysis-form";

type Schema = components["schemas"];
type Document = Schema["KnowledgeDocumentOutput"];
type Detail = Schema["KnowledgeDetail"];
type Preview = Schema["KnowledgePreview"];
type Upload = Schema["KnowledgeUploadOutput"];
type Search = Schema["KnowledgeSearchOutput"];

const states = { indexing: "正在索引", ready: "已就绪", failed: "失败" };

function DocumentRow({
  document,
  selected,
  choose,
}: {
  document: Document;
  selected: boolean;
  choose: () => void;
}) {
  const detail = useQuery({
    queryKey: ["knowledge-detail", document.repo_id, document.id],
    queryFn: () =>
      fetchData<Detail>(`knowledge/${document.id}?repo_id=${document.repo_id}`),
    refetchInterval: 10000,
  });
  const version = detail.data?.versions[0];
  return (
    <button
      className={`knowledge-document ${selected ? "selected" : ""}`}
      onClick={choose}
      type="button"
    >
      <strong>{document.filename}</strong>
      <span>
        {document.source === "fixture" ? "人工样例" : "用户上传"} ·{" "}
        {version
          ? `v${version.number} · ${states[version.status]} · ${version.chunk_count} 块`
          : detail.error
            ? "状态读取失败，点击重试"
            : "读取状态…"}
      </span>
      {version?.error_message && (
        <small className="error-message">{version.error_message}</small>
      )}
    </button>
  );
}

function DocumentPreview({
  repoId,
  documentId,
  initialVersion,
  remove,
  busy,
}: {
  repoId: string;
  documentId: string;
  initialVersion?: string;
  remove: (id: string) => void;
  busy: boolean;
}) {
  const [chosen, setChosen] = useState(initialVersion ?? "");
  const detail = useQuery({
    queryKey: ["knowledge-detail", repoId, documentId],
    queryFn: () =>
      fetchData<Detail>(`knowledge/${documentId}?repo_id=${repoId}`),
    refetchInterval: 10000,
  });
  const versionId = chosen || detail.data?.versions[0]?.id;
  const preview = useQuery({
    queryKey: ["knowledge-preview", repoId, documentId, versionId],
    queryFn: () =>
      fetchData<Preview>(
        `knowledge/${documentId}/versions/${versionId}?repo_id=${repoId}`,
      ),
    enabled: Boolean(versionId),
  });
  const version = preview.data?.version;
  return (
    <section
      className="knowledge-panel knowledge-preview"
      aria-label="文档版本与原文"
    >
      <div className="knowledge-heading">
        <h2>{detail.data?.document.filename ?? "来源预览"}</h2>
        <button
          type="button"
          disabled={busy || detail.data?.document.deleted}
          onClick={() => remove(documentId)}
        >
          删除文档与索引
        </button>
      </div>
      <QueryState
        pending={detail.isPending}
        error={detail.error}
        retry={() => void detail.refetch()}
      />
      <p className="column-intro">
        同名文件再次上传会创建新版本。更新或删除后，新检索只使用有效版本；历史任务引用保留供核查。
      </p>
      <label>
        预览版本
        <select
          value={versionId ?? ""}
          onChange={(event) => setChosen(event.target.value)}
        >
          {detail.data?.versions.map((v) => (
            <option key={v.id} value={v.id}>
              v{v.number} · {states[v.status]}
              {v.is_current ? " · 当前有效" : " · 不参与检索"}
            </option>
          ))}
        </select>
      </label>
      {version && (
        <>
          <p className="hash-note">
            版本 {version.id} · {version.chunk_count} 块 · {version.size_bytes}{" "}
            bytes
          </p>
          <p className="hash-note">原文件 SHA256 {version.raw_sha256}</p>
          {version.error_message && (
            <p className="error-message">
              {version.error_code} · {version.error_message}
            </p>
          )}
          {detail.data?.versions.some(
            (v) => v.is_current && v.id !== version.id,
          ) && (
            <p className="source-warning">
              当前预览版本未生效，检索仍使用此前成功索引的版本。
            </p>
          )}
        </>
      )}
      <QueryState
        pending={Boolean(versionId) && preview.isPending}
        error={preview.error}
        retry={() => void preview.refetch()}
      />
      {preview.data?.page_starts.length ? (
        <p className="hash-note">
          PDF 提取文本行号；
          {preview.data.page_starts
            .map((p) => `第 ${p.page} 页从 L${p.start_line} 开始`)
            .join("；")}
        </p>
      ) : null}
      {preview.data?.content && (
        <div className="code-block evidence-code">
          <ol>
            {preview.data.content
              .replace(/\r\n|\r/g, "\n")
              .split("\n")
              .map((line, index) => (
                <li key={index}>
                  <code>{line || " "}</code>
                </li>
              ))}
          </ol>
        </div>
      )}
      {!preview.data?.content && version?.status === "failed" && (
        <p className="empty-panel">
          解析或索引失败。请根据原因修正后重新上传；失败记录已保留。
        </p>
      )}
    </section>
  );
}

function RepositoryKnowledge({
  repoId,
  available,
}: {
  repoId: string;
  available: boolean;
}) {
  const cache = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [selected, setSelected] = useState<{
    document: string;
    version?: string;
  } | null>(null);
  const [question, setQuestion] = useState(
    "项目对任务所有者隔离和 labels=null 有什么约束？",
  );
  const [mode, setMode] = useState<"hybrid" | "keyword">("hybrid");
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<Search | null>(null);
  const documents = useInfiniteQuery({
    queryKey: ["knowledge", repoId],
    queryFn: ({ pageParam, signal }) =>
      fetchData<Page<Document>>(
        `knowledge?repo_id=${repoId}&limit=20&offset=${pageParam}`,
        { signal },
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: available,
  });
  const items = documents.data?.pages.flatMap((p) => p.items) ?? [];
  const active = selected?.document ?? items[0]?.id;

  async function refresh() {
    setResult(null);
    await cache.invalidateQueries({ queryKey: ["knowledge", repoId] });
    await cache.invalidateQueries({ queryKey: ["knowledge-detail", repoId] });
    await cache.invalidateQueries({ queryKey: ["knowledge-preview", repoId] });
  }
  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file || busy) return;
    setError(null);
    setMessage("");
    if (file.size > 5 * 1024 * 1024) {
      setError(new Error("单文件最大 5 MiB"));
      return;
    }
    setBusy(true);
    try {
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(new Error("文件读取失败"));
        reader.readAsDataURL(file);
      });
      const value = await postData<Upload>("knowledge/upload", {
        repo_id: repoId,
        filename: file.name,
        content_base64: content,
      });
      setSelected({ document: value.document_id, version: value.version.id });
      setMessage(
        value.duplicate
          ? "内容相同，已复用有效文档版本。"
          : value.version.status === "ready"
            ? `索引完成 · v${value.version.number} · ${value.version.chunk_count} 个块`
            : `导入失败：${value.version.error_message}`,
      );
      await refresh();
      if (fileInput.current) fileInput.current.value = "";
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("上传失败"));
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await postData(`knowledge/${id}/delete?repo_id=${repoId}`, {});
      setSelected(null);
      setMessage("文档已删除，关联索引已移除。历史引用仍可核查。");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("删除失败"));
    } finally {
      setBusy(false);
    }
  }
  async function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (searching || !question.trim()) return;
    setSearching(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await postData<Search>("knowledge/search", {
          repo_id: repoId,
          query: question.trim(),
          mode,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("检索失败"));
    } finally {
      setSearching(false);
    }
  }
  if (!available)
    return (
      <p className="empty-panel">
        当前是文件浏览模式。请按 README 切换数据库模式后维护知识库。
      </p>
    );
  return (
    <>
      <section className="knowledge-panel">
        <h2>导入项目资料</h2>
        <p className="column-intro">
          支持 UTF-8 Markdown、TXT 和可提取文本的 PDF（最多 50 页）。单文件 5
          MiB，扫描件暂不支持。同名上传更新版本，相同内容自动去重。
        </p>
        <form
          onSubmit={(event) => void upload(event)}
          className="knowledge-upload"
        >
          <label>
            选择资料
            <input
              ref={fileInput}
              type="file"
              accept=".md,.txt,.pdf"
              required
              disabled={busy}
            />
          </label>
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "正在处理…" : "上传并建立索引"}
          </button>
        </form>
      </section>
      {message && (
        <p role="status" className="source-notice">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="error-message">
          {error.message}
        </p>
      )}
      <div className="knowledge-grid">
        <section className="knowledge-panel">
          <div className="knowledge-heading">
            <h2>仓库资料</h2>
            <button type="button" onClick={() => void refresh()}>
              刷新状态
            </button>
          </div>
          <QueryState
            pending={documents.isPending}
            error={documents.error}
            retry={() => void documents.refetch()}
          />
          {items.length === 0 && documents.data && (
            <p className="empty-panel">
              还没有文档。上传设计约束、故障手册或历史复盘后即可检索。
            </p>
          )}
          {items.map((doc) => (
            <DocumentRow
              key={doc.id}
              document={doc}
              selected={doc.id === active}
              choose={() => setSelected({ document: doc.id })}
            />
          ))}
          {documents.hasNextPage && (
            <button
              disabled={documents.isFetchingNextPage}
              type="button"
              onClick={() => void documents.fetchNextPage()}
            >
              加载更多资料
            </button>
          )}
        </section>
        {active ? (
          <DocumentPreview
            key={`${active}:${selected?.version ?? ""}`}
            repoId={repoId}
            documentId={active}
            initialVersion={selected?.version}
            remove={(id) => void remove(id)}
            busy={busy}
          />
        ) : (
          <section className="knowledge-panel">
            <h2>来源预览</h2>
            <p className="empty-panel">
              选择文档查看索引状态、版本和带行号原文。
            </p>
          </section>
        )}
      </div>
      <section className="knowledge-panel">
        <p className="eyebrow">检索调试</p>
        <h2>查看问题命中了哪些资料</h2>
        <form
          onSubmit={(event) => void search(event)}
          className="knowledge-search"
        >
          <label>
            检索问题
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              required
              maxLength={500}
            />
          </label>
          <label>
            检索方式
            <select
              value={mode}
              onChange={(event) =>
                setMode(event.target.value as "hybrid" | "keyword")
              }
            >
              <option value="hybrid">混合检索 · 向量 + 关键词</option>
              <option value="keyword">仅关键词 · 对照</option>
            </select>
          </label>
          <button
            type="submit"
            className="primary-button"
            disabled={searching || busy}
          >
            {searching ? "检索中…" : "检索资料"}
          </button>
        </form>
        {result && (
          <>
            <p className="column-intro">{result.note}</p>
            {result.items.length === 0 && (
              <p className="empty-panel">
                未命中有效资料，证据不足。请补充文档或调整问题。
              </p>
            )}
            {result.items.map((hit, index) => (
              <article key={hit.chunk_id} className="knowledge-hit">
                <div className="knowledge-heading">
                  <h3>
                    {index + 1}. {hit.filename} · v{hit.version_number}
                  </h3>
                  <button
                    type="button"
                    onClick={() => {
                      setSelected({
                        document: hit.document_id,
                        version: hit.version_id,
                      });
                      document
                        .getElementById("knowledge-top")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    预览来源
                  </button>
                </div>
                <p className="hash-note">
                  {hit.source === "fixture" ? "人工样例" : "用户上传"} · L
                  {hit.start_line}–{hit.end_line}
                  {hit.page ? ` · PDF 第 ${hit.page} 页` : ""} · RRF{" "}
                  {hit.rrf_score.toFixed(5)} · 向量排名{" "}
                  {hit.ranks.vector_rank ?? "—"} / 关键词排名{" "}
                  {hit.ranks.keyword_rank ?? "—"} · 相似度{" "}
                  {hit.vector_similarity?.toFixed(4) ?? "—"}
                </p>
                <pre>{hit.content}</pre>
                <small className="hash-note">
                  证据 {hit.evidence_id} · 版本 {hit.version_id}
                </small>
              </article>
            ))}
          </>
        )}
      </section>
      <AnalysisForm key={repoId} repoId={repoId} taskType="knowledge_qa" />
    </>
  );
}

export function KnowledgeWorkspace({ repoId }: { repoId?: string }) {
  const router = useRouter();
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: () => fetchData<Collection<Repository>>("repositories"),
  });
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: () => fetchData<RuntimeInfo>("runtime"),
  });
  const model = useQuery({
    queryKey: ["knowledge-status"],
    queryFn: () =>
      fetchData<{ model_files_ready: boolean }>("knowledge/status"),
  });
  const chosen = repoId ?? repositories.data?.items[0]?.id;
  const available =
    runtime.data?.data_source === "github" ||
    runtime.data?.fixture_storage === "database";
  return (
    <div className="knowledge-page" id="knowledge-top">
      <p className="eyebrow">项目知识 · RAG</p>
      <div className="knowledge-heading">
        <div>
          <h1>把项目背景带入分析</h1>
          <p className="column-intro">
            资料按仓库和版本隔离，回答与报告中的引用可以逐行核查。
          </p>
        </div>
        <Link className="text-link" href="/repositories">
          回到仓库 →
        </Link>
      </div>
      <div className="knowledge-toolbar">
        <label>
          所属仓库
          <select
            value={chosen ?? ""}
            onChange={(event) =>
              router.push(
                `/knowledge?repo=${encodeURIComponent(event.target.value)}`,
              )
            }
          >
            <option value="" disabled>
              选择仓库
            </option>
            {repositories.data?.items.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.full_name} ·{" "}
                {repo.data_source === "fixture" ? "人工样例" : "GitHub"}
              </option>
            ))}
          </select>
        </label>
        <span className="source-badge">
          {model.data
            ? model.data.model_files_ready
              ? "本地向量模型已下载 · CPU"
              : "本地模型待准备 · 参照 README 初始化"
            : "正在检测本地模型…"}
        </span>
      </div>
      <QueryState
        pending={repositories.isPending || runtime.isPending}
        error={repositories.error ?? runtime.error ?? model.error}
        retry={() => {
          void repositories.refetch();
          void runtime.refetch();
          void model.refetch();
        }}
      />
      {chosen && runtime.data && (
        <RepositoryKnowledge
          key={chosen}
          repoId={chosen}
          available={available}
        />
      )}
      {repositories.data?.items.length === 0 && (
        <p className="empty-panel">请先添加仓库，再导入项目资料。</p>
      )}
    </div>
  );
}
