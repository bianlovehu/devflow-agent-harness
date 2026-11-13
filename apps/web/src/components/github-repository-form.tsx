// 文件用途：登记 GitHub 仓库并手动刷新摘要，所有外部请求保持只读。
"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, fetchData, postData } from "@/lib/api-client";
import type { Repository, RuntimeInfo } from "@/lib/repositories";
import { QueryState } from "@/components/query-state";

export function GitHubRepositoryForm() {
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: () => fetchData<RuntimeInfo>("runtime"),
  });
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const lock = useRef(false);
  const cache = useQueryClient();
  const router = useRouter();
  async function save() {
    if (
      lock.current ||
      !url.trim() ||
      (error instanceof ApiError && (error.retryAt ?? 0) > Date.now())
    )
      return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      const repo = await postData<Repository>("repositories", {
        url: url.trim(),
      });
      cache.setQueryData(["repository", repo.id], repo);
      await cache.invalidateQueries({ queryKey: ["repositories"] });
      router.push(`/repositories/${repo.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("仓库添加失败"));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  if (
    !runtime.data ||
    (runtime.data.data_source !== "github" &&
      runtime.data.fixture_storage !== "database")
  )
    return null;
  return (
    <section
      className="analysis-create github-add"
      aria-labelledby="github-add-title"
    >
      <div>
        <p className="eyebrow">GitHub 只读接入</p>
        <h2 id="github-add-title">添加一个仓库</h2>
        <p className="column-intro">
          先同步最近20条 PR 和 CI 摘要，选择资源后再读取详情。
        </p>
        {!runtime.data.github_configured && (
          <p className="column-intro">
            当前未配置
            Token，可尝试公开仓库。私有仓库和受限日志需要相应的只读权限。
          </p>
        )}
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <label htmlFor="github-url">仓库地址</label>
        <input
          id="github-url"
          value={url}
          disabled={busy}
          maxLength={300}
          required
          placeholder="https://github.com/owner/repo"
          onChange={(event) => {
            setUrl(event.target.value);
            setError(null);
          }}
        />
        <QueryState pending={false} error={error} retry={() => void save()} />
        <div className="form-footer">
          <p>只保存到本地，不修改 GitHub 仓库。</p>
          {!error && (
            <button
              type="submit"
              className="primary-button"
              disabled={busy || !url.trim()}
            >
              {busy ? "正在同步仓库…" : "添加并读取仓库"}
            </button>
          )}
        </div>
      </form>
    </section>
  );
}

export function RepositoryRefresh({ repo }: { repo: Repository }) {
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const lock = useRef(false);
  async function refresh() {
    if (
      lock.current ||
      (error instanceof ApiError && (error.retryAt ?? 0) > Date.now())
    )
      return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await postData<Repository>(
        `repositories/${repo.id}/refresh`,
        {},
      );
      cache.setQueryData(["repository", repo.id], result);
      await Promise.all(
        [
          ["repositories"],
          ["pull-requests", repo.id],
          ["ci-runs", repo.id],
          ["resource-detail", repo.id],
        ].map((queryKey) => cache.invalidateQueries({ queryKey })),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("刷新失败"));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  if (repo.data_source !== "github") return null;
  return (
    <div className="repository-refresh">
      {!error && (
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          {busy ? "正在同步摘要…" : "刷新 GitHub 摘要"}
        </button>
      )}
      <QueryState pending={false} error={error} retry={() => void refresh()} />
    </div>
  );
}
