// 文件用途：按仓库审核、编辑、撤销和替代长期记忆，展示来源与适用版本。
"use client";
import Link from "next/link";
import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { fetchData, postData } from "@/lib/api-client";
import type { components } from "@/lib/generated/api";
import { useWorkspace } from "@/components/workspace-context";
import { Icon } from "@/components/icon";
import type { Page } from "@/lib/workflows";
import { QueryState } from "@/components/query-state";

type Memory = components["schemas"]["MemoryOutput"];
const statuses = {
  pending: "待审核",
  approved: "已批准",
  revoked: "已撤销",
  superseded: "已替代",
};

function MemoryCard({ memory, all }: { memory: Memory; all: Memory[] }) {
  const cache = useQueryClient();
  const [summary, setSummary] = useState(memory.summary);
  const [version, setVersion] = useState(memory.applicable_version ?? "");
  const [specific, setSpecific] = useState(Boolean(memory.applicable_version));
  const [expires, setExpires] = useState(memory.expires_at.slice(0, 10));
  const [replacement, setReplacement] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const editable =
    !memory.expired && ["pending", "approved"].includes(memory.status);
  const dirty =
    summary !== memory.summary ||
    version !== (memory.applicable_version ?? "") ||
    expires !== memory.expires_at.slice(0, 10);
  const valid =
    summary.trim() && expires && (!specific || /^[0-9a-f]{40}$/.test(version));
  async function act(action: "edit" | "approve" | "revoke") {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await postData<Memory>(
        `memories/${memory.id}/${action}?repo_id=${encodeURIComponent(memory.repo_id)}`,
        action === "edit"
          ? {
              summary,
              applicable_version: version || null,
              expires_at: `${expires}T23:59:59Z`,
            }
          : action === "approve"
            ? { replaces_id: replacement || null }
            : {},
      );
      await cache.invalidateQueries({ queryKey: ["memories", memory.repo_id] });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("记忆更新失败"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="memory-detail" aria-label="经验详情与审核">
      <div className="risk-heading">
        <h2>审核经验</h2>
        <span className="source-badge">
          {memory.expired ? "已过期" : statuses[memory.status]}
        </span>
      </div>
      <p className="column-intro">
        {memory.extraction.provider === "fake"
          ? "离线演示候选经验"
          : "模型提出的候选经验"}
      </p>
      {editable ? (
        <>
          <label>
            经验内容
            <textarea
              value={summary}
              disabled={busy}
              maxLength={2000}
              onChange={(e) => setSummary(e.target.value)}
            />
          </label>
          <div className="memory-field-row">
            <label>
              适用范围
              <select
                value={specific ? "commit" : "repository"}
                disabled={busy}
                onChange={(e) => {
                  setSpecific(e.target.value === "commit");
                  if (e.target.value === "repository") setVersion("");
                }}
              >
                <option value="repository">本仓库通用</option>
                <option value="commit">指定提交版本</option>
              </select>
            </label>
            <label>
              有效期至
              <input
                type="date"
                value={expires}
                disabled={busy}
                onChange={(e) => setExpires(e.target.value)}
              />
            </label>
          </div>
          {specific && (
            <label>
              适用提交
              <input
                value={version}
                disabled={busy}
                maxLength={40}
                placeholder="输入完整的 40 位提交 SHA"
                onChange={(e) => setVersion(e.target.value)}
              />
            </label>
          )}
        </>
      ) : (
        <>
          <h3>经验内容</h3>
          <p className="memory-summary">{memory.summary}</p>
          <p className="column-intro">
            适用版本：{memory.applicable_version ?? "本仓库通用"}
            <br />
            有效期至：{new Date(memory.expires_at).toLocaleString("zh-CN")}
          </p>
        </>
      )}
      <div className="memory-source-heading">
        <h3>来源依据</h3>
        <Link className="text-link" href={`/runs/${memory.source_run_id}`}>
          查看来源报告 ↗
        </Link>
      </div>
      <Link className="memory-source" href={`/runs/${memory.source_run_id}`}>
        <Icon name="file" size={17} />
        分析报告 · {memory.source_run_id.slice(0, 8)}
        <Icon name="external" size={15} />
      </Link>
      <details className="memory-sources">
        <summary>来源引用 · {memory.sources.length} 条</summary>
        <pre>{JSON.stringify(memory.sources, null, 2)}</pre>
      </details>
      {memory.status === "pending" && !memory.expired && (
        <label>
          批准时替代旧经验（可选）
          <select
            value={replacement}
            disabled={busy}
            onChange={(e) => setReplacement(e.target.value)}
          >
            <option value="">不替代</option>
            {all
              .filter(
                (m) =>
                  m.id !== memory.id && m.status === "approved" && !m.expired,
              )
              .map((m) => (
                <option value={m.id} key={m.id}>
                  {m.summary.slice(0, 60)}
                </option>
              ))}
          </select>
        </label>
      )}
      <div className="memory-detail-actions">
        {editable && (
          <button
            disabled={busy || !dirty || !valid}
            onClick={() => void act("edit")}
          >
            保存为待审核
          </button>
        )}
        {["pending", "approved"].includes(memory.status) && (
          <button disabled={busy} onClick={() => void act("revoke")}>
            撤销
          </button>
        )}
        {memory.status === "pending" && !memory.expired && (
          <button
            className="primary-button"
            disabled={busy || dirty || !valid}
            onClick={() => void act("approve")}
          >
            批准召回
          </button>
        )}
      </div>
      {dirty && (
        <p className="column-intro" role="status">
          编辑后请先保存，再批准。指定提交需填写完整 SHA。
        </p>
      )}
      <QueryState pending={false} error={error} retry={() => setError(null)} />
      <p className="memory-policy">
        只有已批准、未过期且适用范围匹配的经验会用于后续分析。
      </p>
    </article>
  );
}

export function ExtractMemory({
  runId,
  findingIndex,
}: {
  runId: string;
  findingIndex?: number;
}) {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Memory | null>(null);
  const [error, setError] = useState("");
  async function extract() {
    setBusy(true);
    setError("");
    try {
      setSaved(
        await postData<Memory>(`runs/${runId}/memories`, {
          finding_index: findingIndex ?? null,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "提取失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="memory-extract">
      {saved ? (
        <Link href={`/memories?repo=${encodeURIComponent(saved.repo_id)}`}>
          候选已保存，前往审核
        </Link>
      ) : (
        <button type="button" disabled={busy} onClick={() => void extract()}>
          {busy ? "正在提取经验…" : "提取经验"}
        </button>
      )}
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
    </div>
  );
}

function RepositoryMemories({ repoId }: { repoId: string }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [chosen, setChosen] = useState("");
  const memories = useInfiniteQuery({
    queryKey: ["memories", repoId],
    queryFn: ({ pageParam, signal }) =>
      fetchData<Page<Memory>>(
        `memories?repo_id=${encodeURIComponent(repoId)}&offset=${pageParam}`,
        { signal },
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    refetchInterval: 30000,
  });
  const items = memories.data?.pages.flatMap((p) => p.items) ?? [];
  const stateOf = (m: Memory) => (m.expired ? "expired" : m.status);
  const matches = items.filter(
    (m) =>
      (filter === "all" || stateOf(m) === filter) &&
      m.summary.toLowerCase().includes(search.toLowerCase()),
  );
  const active = matches.find((m) => m.id === chosen) ?? matches[0];
  const filters = [
    ["all", "全部"],
    ["pending", "待审核"],
    ["approved", "已批准"],
    ["revoked", "已撤销"],
    ["superseded", "已替代"],
    ["expired", "已过期"],
  ];
  return (
    <>
      <div className="memory-filter-tabs" aria-label="经验状态筛选">
        {filters.map(([key, label]) => (
          <button
            key={key}
            className={filter === key ? "tab-active" : ""}
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {label}
            <span>
              {items.filter((m) => key === "all" || stateOf(m) === key).length}
              {memories.hasNextPage ? "+" : ""}
            </span>
          </button>
        ))}
      </div>
      <QueryState
        pending={memories.isPending}
        error={memories.error}
        retry={() => void memories.refetch()}
      />
      <div className="memory-master-detail">
        <aside className="memory-catalog" aria-label="经验列表">
          <label className="search-input">
            <Icon name="search" size={18} />
            <input
              aria-label="搜索经验"
              placeholder="搜索经验…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div className="memory-list">
            {matches.map((memory) => (
              <button
                key={memory.id}
                className={
                  active?.id === memory.id
                    ? "memory-choice selected"
                    : "memory-choice"
                }
                aria-pressed={active?.id === memory.id}
                onClick={() => setChosen(memory.id)}
              >
                <strong>{memory.summary}</strong>
                <span>
                  {memory.expired ? "已过期" : statuses[memory.status]} ·
                  来源报告 {memory.source_run_id.slice(0, 8)}
                </span>
                <small>
                  有效期至{" "}
                  {new Date(memory.expires_at).toLocaleDateString("zh-CN")}
                </small>
              </button>
            ))}
          </div>
          {memories.isSuccess && !matches.length && (
            <p className="empty-panel">
              {items.length
                ? "暂无匹配经验，请调整筛选。"
                : "还没有经验。从已完成报告中选择「提取经验」。"}
            </p>
          )}
          {memories.hasNextPage && (
            <button
              className="text-button"
              disabled={memories.isFetchingNextPage}
              onClick={() => void memories.fetchNextPage()}
            >
              加载更多经验
            </button>
          )}
          <p className="column-intro">
            从分析报告中选择「提取经验」可新增候选。
            {memories.hasNextPage && "筛选仅覆盖当前已加载的经验。"}
          </p>
        </aside>
        {active ? (
          <MemoryCard
            key={`${active.id}:${active.status}:${active.expires_at}:${active.applicable_version}:${active.summary}`}
            memory={active}
            all={items}
          />
        ) : (
          <div className="memory-detail selection-hint">
            <Icon name="memory" size={36} />
            <h2>选择一条经验</h2>
            <p>核查来源、编辑适用范围并审核。</p>
          </div>
        )}
      </div>
    </>
  );
}
export function MemoryWorkspace({ repoId: initialRepo }: { repoId?: string }) {
  const { repoId, repositories, available, runtime } = useWorkspace();
  const selected = initialRepo ?? repoId;
  return (
    <section className="management-page memory-workspace">
      <div className="page-heading">
        <div>
          <h1>长期记忆</h1>
          <p className="intro">审核项目经验，决定后续分析可以使用哪些记忆</p>
        </div>
      </div>
      <QueryState
        pending={repositories.isPending || runtime.isPending}
        error={repositories.error ?? runtime.error}
        retry={() => {
          void repositories.refetch();
          void runtime.refetch();
        }}
      />
      {selected &&
      available &&
      repositories.data?.items.some((r) => r.id === selected) ? (
        <RepositoryMemories key={selected} repoId={selected} />
      ) : (
        runtime.data && (
          <p className="empty-panel">
            {!available
              ? "数据库模式下可审核和保存长期记忆。"
              : "请先添加或选择有效仓库。"}
          </p>
        )
      )}
    </section>
  );
}
