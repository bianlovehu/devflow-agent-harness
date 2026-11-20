// 文件用途：固定提交代码工作台，目录、字面量搜索与带行号的只读阅读。
"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchData, postData } from "@/lib/api-client";
import { codeLine, codeLocation } from "@/lib/code-location";
import { loadRootReadme } from "@/lib/code-readme";
import type {
  CodeFile,
  CodeSearch,
  CodeSnapshot,
  CodeSnapshotSelection,
  CodeTree,
} from "@/lib/code";
import type { Repository } from "@/lib/repositories";
import { useWorkspace } from "@/components/workspace-context";
import { QueryState } from "@/components/query-state";
import "./code-workspace.css";

const states: Record<string, string> = {
  queued: "等待 worker 准备",
  preparing: "正在准备代码",
  ready: "快照就绪",
  partial: "快照部分就绪",
  failed: "快照准备失败",
};
const reasons: Record<string, string> = {
  unsupported_type: "文件类型不支持",
  unsupported_encoding: "不是有效 UTF-8",
  binary_file: "二进制文件",
  sensitive_file: "敏感凭据文件",
  excluded_directory: "已排除的依赖或构建目录",
  file_too_large: "文件超过 256 KiB",
  snapshot_budget: "超出快照容量限制",
  archive_omitted: "归档未包含此文件",
  symlink_or_submodule: "不跟随链接或子模块",
  invalid_path: "路径不受支持",
};

function Directory({
  base,
  sid,
  path = "",
  selected,
  choose,
}: {
  base: string;
  sid: string;
  path?: string;
  selected: string;
  choose: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["code-tree", base, sid, path, offset],
    queryFn: ({ signal }) =>
      fetchData<CodeTree>(
        `${base}/tree?${new URLSearchParams({ snapshot_id: sid, path, offset: String(offset) })}`,
        { signal },
      ),
  });
  return (
    <div className="code-directory">
      <QueryState
        pending={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
      />
      {query.data?.items.map((item) => (
        <div key={item.path}>
          <button
            className={selected === item.path ? "code-selected" : ""}
            title={
              item.skip_reason
                ? (reasons[item.skip_reason] ?? item.skip_reason)
                : item.path
            }
            onClick={() =>
              item.kind === "directory"
                ? setExpanded((value) => {
                    const next = new Set(value);
                    if (next.has(item.path)) next.delete(item.path);
                    else next.add(item.path);
                    return next;
                  })
                : choose(item.path)
            }
          >
            {item.kind === "directory"
              ? expanded.has(item.path)
                ? "▾ "
                : "▸ "
              : "· "}
            {item.path.split("/").at(-1)}
            {item.skip_reason && " ⓘ"}
          </button>
          {item.kind === "directory" && expanded.has(item.path) && (
            <Directory
              base={base}
              sid={sid}
              path={item.path}
              selected={selected}
              choose={choose}
            />
          )}
        </div>
      ))}
      {query.data?.items.length === 0 && <p>此目录没有已登记文件。</p>}
      <div className="code-paging">
        {offset > 0 && (
          <button onClick={() => setOffset(Math.max(0, offset - 100))}>
            上一页
          </button>
        )}
        {query.data?.next_offset != null && (
          <button onClick={() => setOffset(query.data!.next_offset!)}>
            下一页
          </button>
        )}
      </div>
    </div>
  );
}

export function CodeWorkspace({ repoId }: { repoId: string }) {
  const router = useRouter();
  const cache = useQueryClient();
  const actionLock = useRef(false);
  const autoReadmeTarget = useRef<string | false | null>(null);
  const [pulling, setPulling] = useState(false);
  const { runtime } = useWorkspace();
  const params = useSearchParams();
  const base = `repositories/${encodeURIComponent(repoId)}/code`;
  const commit = params.get("commit") ?? "";
  const sid = params.get("snapshot_id") ?? "";
  const path = params.get("path") ?? "";
  const line = codeLine(params.get("line"));
  const end = Math.max(line, codeLine(params.get("end")));
  const [term, setTerm] = useState("");
  const [search, setSearch] = useState<CodeSearch | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [copyMessage, setCopyMessage] = useState("");
  const repo = useQuery({
    queryKey: ["repository", repoId],
    queryFn: ({ signal }) =>
      fetchData<Repository>(`repositories/${encodeURIComponent(repoId)}`, {
        signal,
      }),
  });
  const cached = useQuery({
    queryKey: ["code-cached", repoId, commit],
    queryFn: ({ signal }) =>
      fetchData<CodeSnapshotSelection>(
        `${base}/snapshots${commit ? `?commit=${encodeURIComponent(commit)}` : ""}`,
        { signal },
      ),
    enabled: !sid,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
  const snapshot = useQuery({
    queryKey: ["code-snapshot", repoId, sid],
    queryFn: ({ signal }) =>
      fetchData<CodeSnapshot>(`${base}/snapshots/${sid}`, { signal }),
    enabled: Boolean(sid),
    refetchInterval: (query) =>
      ["queued", "preparing"].includes(query.state.data?.status ?? "")
        ? 1500
        : false,
  });
  const data = snapshot.data ?? (!sid ? cached.data?.snapshot : undefined);
  const mismatch = Boolean(data && commit && data.commit !== commit);
  const ready = Boolean(
    data && ["ready", "partial"].includes(data.status) && !mismatch,
  );
  useEffect(() => {
    if (!sid && data && !pulling && !cached.isFetching)
      router.replace(
        codeLocation(repoId, data.commit, path, line, end, data.snapshot_id),
        { scroll: false },
      );
  }, [sid, data, pulling, cached.isFetching, router, repoId, path, line, end]);
  const readme = useQuery({
    queryKey: ["code-readme", repoId, sid],
    queryFn: ({ signal }) =>
      loadRootReadme(async (offset) => {
        signal.throwIfAborted();
        const key = ["code-tree", base, sid, "", offset];
        const saved = cache.getQueryData<CodeTree>(key);
        if (saved) return saved;
        // 复用已完成的目录页；独立请求避免目录卸载时取消 README 定位。
        const page = await fetchData<CodeTree>(
          `${base}/tree?${new URLSearchParams({ snapshot_id: sid, path: "", offset: String(offset) })}`,
          { signal },
        );
        cache.setQueryData(key, page);
        return page;
      }),
    enabled: ready && Boolean(sid) && !path && !pulling,
    retry: false,
    staleTime: Infinity,
  });
  useEffect(() => {
    // 手动选择文件优先；拉取期间不让旧快照的异步结果覆盖新地址。
    const target = autoReadmeTarget.current;
    if (
      ready &&
      !path &&
      !pulling &&
      sid &&
      data?.snapshot_id === sid &&
      readme.data &&
      target !== false &&
      (target === null || target === sid)
    )
      router.replace(
        codeLocation(repoId, data.commit, readme.data, 1, 1, sid),
        { scroll: false },
      );
  }, [ready, path, pulling, sid, data, readme.data, router, repoId]);
  const file = useQuery({
    queryKey: ["code-file", repoId, sid, path, line],
    queryFn: ({ signal }) =>
      fetchData<CodeFile>(
        `${base}/file?${new URLSearchParams({ snapshot_id: sid, path, start_line: String(line), limit: "60" })}`,
        { signal },
      ),
    enabled: ready && Boolean(sid && path),
  });
  function choose(nextPath: string, start = 1, finish = start) {
    autoReadmeTarget.current = false;
    if (data)
      router.push(
        codeLocation(
          repoId,
          data.commit,
          nextPath,
          start,
          finish,
          data.snapshot_id,
        ),
        { scroll: false },
      );
  }
  async function runSearch() {
    if (!data || searching) return;
    setSearching(true);
    setError(null);
    setSearch(null);
    try {
      setSearch(
        await postData<CodeSearch>(`${base}/search`, {
          snapshot_id: data.snapshot_id,
          query: term,
          mode: "snippets",
          limit: 20,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("搜索失败"));
    } finally {
      setSearching(false);
    }
  }
  async function pullCode(latest = false) {
    if (actionLock.current) return;
    actionLock.current = true;
    autoReadmeTarget.current = false;
    setPulling(true);
    setError(null);
    try {
      const row = await postData<CodeSnapshot>(
        latest ? `${base}/pull` : `${base}/snapshots`,
        latest ? {} : { commit: data?.commit ?? commit, retry: true },
      );
      autoReadmeTarget.current = row.snapshot_id;
      cache.setQueryData(["code-snapshot", repoId, row.snapshot_id], row);
      setSearch(null);
      router.push(codeLocation(repoId, row.commit, "", 1, 1, row.snapshot_id), {
        scroll: false,
      });
      await cache.invalidateQueries({ queryKey: ["repository", repoId] });
      await cache.invalidateQueries({ queryKey: ["code-cached", repoId] });
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("拉取失败"));
    } finally {
      setPulling(false);
      actionLock.current = false;
    }
  }
  return (
    <div className="code-workspace">
      <p className="code-intro">
        默认浏览本地已保存的代码，不会在访问时自动拉取；更新仓库后可手动拉取最新代码。已准备文件不代表模型已经阅读。
      </p>
      <div className="code-actions">
        <button disabled={pulling} onClick={() => void pullCode(true)}>
          {pulling
            ? "正在请求拉取…"
            : repo.data?.data_source === "fixture"
              ? "准备样例代码"
              : "拉取最新代码"}
        </button>
        <span>相同提交复用本地快照；历史版本保留。</span>
      </div>
      <QueryState
        pending={
          (!sid && cached.isPending) || (Boolean(sid) && snapshot.isPending)
        }
        error={sid ? snapshot.error : cached.error}
        retry={() => void (sid ? snapshot.refetch() : cached.refetch())}
      />
      {error && <p role="alert">{error.message}</p>}
      {!sid && cached.isSuccess && !data && (
        <section className="code-status">
          <strong>{commit ? "此提交尚未保存到本地" : "尚未拉取代码"}</strong>
          <p>点击拉取后会准备并保存代码，后续访问直接复用，不会自动下载。</p>
          {commit && (
            <button disabled={pulling} onClick={() => void pullCode()}>
              拉取此固定提交
            </button>
          )}
        </section>
      )}
      {mismatch && (
        <p role="alert">
          链接提交与快照不一致，请检查链接；不会切换到其他版本。
        </p>
      )}
      {data && (
        <section className="code-status" aria-live="polite">
          <strong>{states[data.status]}</strong>
          <p>
            本地固定提交 <code>{data.commit}</code> ·{" "}
            {repo.data?.default_commit === data.commit
              ? "当前默认提交"
              : "历史或任务提交"}
          </p>
          {data.manifest_sha256 && (
            <details>
              <summary>覆盖与完整性</summary>
              <p>
                清单 SHA256 <code>{data.manifest_sha256}</code>
              </p>
              <p>
                已保存 {String(data.coverage.saved_files ?? 0)}{" "}
                个文件；清单完整：
                {data.coverage.inventory_complete === true ? "是" : "否或未知"}
                ；范围内文本完整：
                {data.coverage.eligible_complete === true ? "是" : "否或未知"}。
              </p>
              <p>
                排除项：
                {Object.entries(
                  (data.coverage.excluded ?? {}) as Record<string, number>,
                )
                  .map(([key, value]) => `${reasons[key] ?? key} ${value}`)
                  .join("；") || "无"}
              </p>
            </details>
          )}
          {data.status === "partial" && (
            <p role="status">
              覆盖不全：浏览和搜索仅涵盖已保存文件，未命中不能证明仓库中不存在。
            </p>
          )}
          {["queued", "preparing"].includes(data.status) && (
            <p>
              正在等待后台准备；请确认 worker
              已启动。导入和此阶段不会调用付费模型。
            </p>
          )}
          {data.error_message && (
            <p role="alert">
              {data.error_message}（{data.error_code}）
            </p>
          )}
          {data.status === "failed" && (
            <button disabled={pulling} onClick={() => void pullCode()}>
              重新准备此提交
            </button>
          )}
          {data.status === "failed" && (
            <button
              onClick={() => router.push(`/repositories/${repoId}?tab=code`)}
            >
              返回代码首页
            </button>
          )}
          <button
            onClick={() => {
              void navigator.clipboard.writeText(window.location.href).then(
                () => setCopyMessage("链接已复制"),
                () => setCopyMessage("复制失败，请复制地址栏链接"),
              );
            }}
          >
            复制当前代码链接
          </button>{" "}
          <span role="status">{copyMessage}</span>
        </section>
      )}
      {runtime.data?.code_search_available === false && (
        <p role="status">
          搜索工具未就绪，文件浏览仍可使用；请配置服务端 CODE_RG_PATH。
        </p>
      )}
      {ready && data && (
        <>
          <form
            className="code-search-form"
            onSubmit={(event) => {
              event.preventDefault();
              void runSearch();
            }}
          >
            <label htmlFor="code-query">字面量搜索</label>
            <input
              id="code-query"
              maxLength={500}
              value={term}
              placeholder="搜索函数名、配置项或报错文本"
              onChange={(event) => setTerm(event.target.value)}
            />
            <button disabled={!term || searching}>
              {searching ? "搜索中…" : "搜索"}
            </button>
          </form>
          {search && search.snapshot_id === data.snapshot_id && (
            <section className="code-results">
              <h2>搜索结果（{search.items.length}）</h2>
              {search.truncated && (
                <p role="status">
                  结果不完整：{search.truncation_reason}，请缩小查询。最多显示
                  20 个命中片段。
                </p>
              )}
              {search.items.length === 0 && (
                <p>
                  {search.search_complete
                    ? "已保存文本中没有匹配。"
                    : "搜索未完成，不能判定没有匹配。"}
                </p>
              )}
              {search.items.map((hit) => (
                <button
                  key={`${hit.path}:${hit.match_line}`}
                  onClick={() => choose(hit.path, hit.match_line)}
                >
                  <strong>
                    {hit.path}：{hit.match_line}
                  </strong>
                  <pre>
                    {hit.lines
                      ?.map((value) => `${value.line}  ${value.text}`)
                      .join("\n")}
                  </pre>
                </button>
              ))}
            </section>
          )}
          <div className="code-columns">
            <aside aria-label="代码目录">
              <h2>目录</h2>
              <Directory
                key={data.snapshot_id}
                base={base}
                sid={data.snapshot_id}
                selected={path}
                choose={choose}
              />
            </aside>
            <section aria-label="代码阅读器">
              <h2>{path || "选择一个文件"}</h2>
              {!path && (
                <>
                  <QueryState
                    pending={Boolean(sid) && readme.isPending}
                    error={readme.error}
                    retry={() => void readme.refetch()}
                  />
                  {readme.isSuccess && !readme.data && (
                    <p>
                      根目录暂无可预览的 README，可从目录或搜索结果打开文件。
                    </p>
                  )}
                </>
              )}
              {path && (
                <QueryState
                  pending={file.isPending}
                  error={file.error}
                  retry={() => void file.refetch()}
                />
              )}
              {file.data && (
                <>
                  <p className="code-file-meta">
                    L{file.data.start_line}–L{file.data.end_line} /{" "}
                    {file.data.line_count} · {file.data.size_bytes} 字节
                  </p>
                  <details>
                    <summary>文件哈希</summary>
                    <p>
                      Git blob{" "}
                      <code>{file.data.blob_sha ?? "样例无远端映射"}</code>
                    </p>
                    <p>
                      SHA256 <code>{file.data.content_sha256}</code>
                    </p>
                    <p>{file.data.redaction_note}</p>
                  </details>
                  <ol className="code-source" start={file.data.start_line}>
                    {file.data.lines.map((value) => (
                      <li
                        key={value.line}
                        className={
                          value.line >= line && value.line <= end
                            ? "evidence-highlight"
                            : ""
                        }
                      >
                        <code>{value.text || " "}</code>
                      </li>
                    ))}
                  </ol>
                  <div className="code-paging">
                    {line > 1 && (
                      <button
                        onClick={() => choose(path, Math.max(1, line - 60))}
                      >
                        上一段
                      </button>
                    )}
                    {file.data.next_line && (
                      <button
                        onClick={() => choose(path, file.data!.next_line!)}
                      >
                        下一段
                      </button>
                    )}
                  </div>
                </>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
