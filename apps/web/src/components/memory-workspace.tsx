// 文件用途：按仓库审核、编辑、撤销和替代长期记忆，展示来源与适用版本。
"use client";
import Link from "next/link";
import { useState } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { fetchData, postData } from "@/lib/api-client";
import type { components } from "@/lib/generated/api";
import type { Collection, Repository } from "@/lib/repositories";
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
    <article className="memory-card">
      <div className="risk-heading">
        <strong>{memory.expired ? "已过期" : statuses[memory.status]}</strong>
        <Link href={`/runs/${memory.source_run_id}`}>查看来源报告</Link>
      </div>
      <p>{memory.summary}</p>
      <p className="hash-note">
        适用版本：{memory.applicable_version ?? "本仓库通用（经人工审核）"}
        <br />
        有效期至：{new Date(memory.expires_at).toLocaleString("zh-CN")}
      </p>
      <details>
        <summary>来源引用 · {memory.sources.length} 条</summary>
        <pre>{JSON.stringify(memory.sources, null, 2)}</pre>
      </details>
      <p className="column-intro">
        {memory.extraction.provider === "fake"
          ? "离线规则演示候选"
          : "模型提出的候选经验"}{" "}
        · 编辑后需重新批准
      </p>
      {editable && (
        <details>
          <summary>编辑经验与适用范围</summary>
          <label>
            经验摘要
            <textarea
              value={summary}
              maxLength={2000}
              onChange={(e) => setSummary(e.target.value)}
            />
          </label>
          <label>
            适用提交（完整 SHA；留空表示本仓库通用）
            <input
              value={version}
              maxLength={40}
              onChange={(e) => setVersion(e.target.value)}
            />
          </label>
          <label>
            有效期
            <input
              type="date"
              value={expires}
              onChange={(e) => setExpires(e.target.value)}
            />
          </label>
          <button
            disabled={
              busy ||
              !summary.trim() ||
              !expires ||
              (Boolean(version) && !/^[0-9a-f]{40}$/.test(version))
            }
            onClick={() => void act("edit")}
          >
            保存为待审核
          </button>
        </details>
      )}
      {memory.status === "pending" && !memory.expired && (
        <label>
          批准时替代旧经验（可选）
          <select
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
          >
            <option value="">不替代</option>
            {all
              .filter(
                (m) =>
                  m.id !== memory.id && m.status === "approved" && !m.expired,
              )
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.summary.slice(0, 60)}
                </option>
              ))}
          </select>
        </label>
      )}
      <div className="report-actions">
        {memory.status === "pending" && !memory.expired && (
          <button disabled={busy || dirty} onClick={() => void act("approve")}>
            批准召回
          </button>
        )}
        {["pending", "approved"].includes(memory.status) && (
          <button disabled={busy} onClick={() => void act("revoke")}>
            撤销
          </button>
        )}
      </div>
      {dirty && memory.status === "pending" && (
        <p className="column-intro">请先保存修改，再批准召回。</p>
      )}
      <QueryState pending={false} error={error} retry={() => setError(null)} />
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

export function MemoryWorkspace({ repoId: initialRepo }: { repoId?: string }) {
  const [chosen, setChosen] = useState(initialRepo ?? "");
  const repos = useQuery({
    queryKey: ["repositories"],
    queryFn: ({ signal }) =>
      fetchData<Collection<Repository>>("repositories", { signal }),
  });
  const repoId = chosen || repos.data?.items[0]?.id;
  const memories = useInfiniteQuery({
    queryKey: ["memories", repoId],
    queryFn: ({ pageParam, signal }) =>
      fetchData<Page<Memory>>(
        `memories?repo_id=${encodeURIComponent(repoId!)}&offset=${pageParam}`,
        { signal },
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: Boolean(repoId),
    refetchInterval: 30000,
  });
  const items = memories.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <section className="memory-workspace">
      <p className="eyebrow">项目经验</p>
      <h1>长期记忆</h1>
      <p>
        从报告提取经验，编辑并批准后用于新分析。默认有效期 30
        天，代码版本不匹配时不会自动注入。
      </p>
      <label>
        所属仓库
        <select
          value={repoId ?? ""}
          onChange={(e) => setChosen(e.target.value)}
        >
          {repos.data?.items.map((repo) => (
            <option key={repo.id} value={repo.id}>
              {repo.full_name}
            </option>
          ))}
        </select>
      </label>
      <QueryState
        pending={repos.isPending || (Boolean(repoId) && memories.isPending)}
        error={repos.error ?? memories.error}
        retry={() => {
          void repos.refetch();
          void memories.refetch();
        }}
      />
      {items.map((memory) => (
        <MemoryCard
          key={`${memory.id}:${memory.status}:${memory.expires_at}:${memory.summary}`}
          memory={memory}
          all={items}
        />
      ))}
      {repoId && memories.data && !items.length && (
        <p className="empty-panel">
          还没有经验。打开已完成的报告，选择“提取经验”。
        </p>
      )}
      {memories.hasNextPage && (
        <button
          disabled={memories.isFetchingNextPage}
          onClick={() => void memories.fetchNextPage()}
        >
          加载更多经验
        </button>
      )}
    </section>
  );
}
