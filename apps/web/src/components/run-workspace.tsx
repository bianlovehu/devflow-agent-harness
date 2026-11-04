// 文件用途：展示可重开的会话、任务详情、已保存事件与固定版本证据。
"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { fetchData } from "@/lib/api-client";
import type { Collection, Repository, RuntimeInfo } from "@/lib/repositories";
import type {
  ArtifactContent,
  Conversation,
  Evidence,
  Page,
  Run,
} from "@/lib/workflows";
import { readMessages, runStatus, taskName } from "@/lib/workflows";
import { activeRun, RunControls, RunProgress } from "@/components/run-progress";
import { QueryState } from "@/components/query-state";
import { AnalysisReport } from "@/components/analysis-report";

function date(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function useRevealSelection(selectedId: string | undefined, itemCount: number) {
  const scrollArea = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const area = scrollArea.current;
    const selected = area?.querySelector('[aria-current="true"]');
    if (!area || !selected) return;
    const bounds = area.getBoundingClientRect();
    const item = selected.getBoundingClientRect();
    // 只移动列表自身，避免切换历史任务时把整页滚到侧栏。
    if (item.top < bounds.top) area.scrollTop += item.top - bounds.top;
    else if (item.bottom > bounds.bottom)
      area.scrollTop += item.bottom - bounds.bottom;
  }, [selectedId, itemCount]);
  return scrollArea;
}
function versionOf(run: Run) {
  const resources = run.input_version.resources;
  if (!Array.isArray(resources)) return "未记录版本";
  const fixed = resources
    .map((item) =>
      String(item.head_sha ?? item.version ?? item.content_sha256 ?? ""),
    )
    .join(" · ");
  const versions = run.input_version.knowledge_versions;
  const knowledge = Array.isArray(versions)
    ? versions.map((id) => `文档 ${String(id).slice(0, 8)}`).join(" · ")
    : "";
  return [fixed, knowledge].filter(Boolean).join(" · ") || "未绑定可用资料版本";
}

function SourceLines({
  content,
  start,
  end,
  full = false,
}: {
  content: string;
  start: number;
  end: number;
  full?: boolean;
}) {
  const lines = content.replace(/\r\n|\r/g, "\n").split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  const from = full ? 0 : Math.max(0, start - 4);
  const to = full ? lines.length : Math.min(lines.length, end + 3);
  return (
    <div className="code-block evidence-code">
      <ol start={from + 1}>
        {lines.slice(from, to).map((line, i) => (
          <li
            key={from + i}
            className={
              from + i + 1 >= start && from + i + 1 <= end
                ? "evidence-highlight"
                : ""
            }
          >
            <code>{line || " "}</code>
          </li>
        ))}
      </ol>
    </div>
  );
}

function EvidencePanel({ run }: { run: Run }) {
  const [selectedId, setSelectedId] = useState("");
  const evidence = useQuery({
    queryKey: ["run-evidence", run.id],
    refetchInterval: activeRun(run) ? 3000 : false,
    queryFn: ({ signal }) =>
      fetchData<Page<Evidence>>(`runs/${run.id}/evidence`, { signal }),
  });
  const selected =
    evidence.data?.items.find((item) => item.id === selectedId) ??
    evidence.data?.items[0];
  const artifact = useQuery({
    queryKey: ["artifact", run.repo_id, selected?.artifact_id],
    queryFn: ({ signal }) =>
      fetchData<ArtifactContent>(
        `artifacts/${selected!.artifact_id}?repo_id=${encodeURIComponent(run.repo_id)}`,
        { signal },
      ),
    enabled: Boolean(selected),
  });
  return (
    <aside className="evidence-panel" aria-label="固定版本证据">
      <div className="column-heading">
        <h2>证据</h2>
        <span>{evidence.data?.items.length ?? 0} 条</span>
      </div>
      <p className="column-intro">任务固定的原始版本；采集完成后可查</p>
      <QueryState
        pending={evidence.isPending}
        error={evidence.error}
        retry={() => void evidence.refetch()}
      />
      {evidence.data?.items.length === 0 && (
        <div className="empty-panel">此任务尚无证据。</div>
      )}
      <div className="evidence-list">
        {evidence.data?.items.map((item) => (
          <button
            type="button"
            key={item.id}
            className={
              item.id === selected?.id
                ? "evidence-choice selected"
                : "evidence-choice"
            }
            onClick={() => setSelectedId(item.id)}
            aria-pressed={item.id === selected?.id}
          >
            <strong>{item.path}</strong>
            <span>
              {item.source_type === "log"
                ? "日志"
                : item.source_type === "file"
                  ? "文件"
                  : item.source_type === "diff"
                    ? "变更"
                    : "资料"}{" "}
              · L{item.start_line}–{item.end_line} · {item.version.slice(0, 8)}
            </span>
          </button>
        ))}
      </div>
      {selected && (
        <section className="evidence-preview" key={selected.id}>
          <h3>{selected.path}</h3>
          <p className="hash-note">
            证据 ID <code>{selected.id}</code>
          </p>
          <p className="evidence-location">
            第 {selected.start_line}–{selected.end_line} 行
          </p>
          <dl className="version-facts">
            <dt>固定版本</dt>
            <dd>
              <code>{selected.version}</code>
            </dd>
            <dt>保存时间</dt>
            <dd>{date(selected.retrieved_at)}</dd>
          </dl>
          <QueryState
            pending={artifact.isPending}
            error={artifact.error}
            retry={() => void artifact.refetch()}
          />
          {artifact.data && (
            <>
              <SourceLines
                content={artifact.data.content}
                start={selected.start_line}
                end={selected.end_line}
              />
              <details className="artifact-full">
                <summary>查看完整原文</summary>
                <SourceLines
                  content={artifact.data.content}
                  start={selected.start_line}
                  end={selected.end_line}
                  full
                />
              </details>
              <p className="hash-note">
                制品 SHA256 <code>{artifact.data.artifact.sha256}</code>
              </p>
            </>
          )}
        </section>
      )}
    </aside>
  );
}

function TaskContent({ run }: { run: Run }) {
  const messages = useQuery({
    queryKey: ["messages", run.conversation_id],
    queryFn: ({ signal }) => readMessages(run.conversation_id, signal),
  });
  const question = messages.data?.find((item) => item.id === run.message_id);
  return (
    <section className="task-content" aria-label="任务详情与报告">
      <div className="column-heading">
        <h2>
          {taskName[run.task_type]} {run.target_id && `#${run.target_id}`}
        </h2>
        <span className={`run-status status-${run.status}`}>
          {runStatus[run.status]}
        </span>
      </div>
      <p className="task-id">任务 {run.id}</p>
      <RunControls run={run} />
      <div className="task-version">
        <span>分析依据的版本</span>
        <code>{versionOf(run)}</code>
        <details>
          <summary>查看输入版本记录</summary>
          <pre>{JSON.stringify(run.input_version, null, 2)}</pre>
        </details>
      </div>
      <h3>本次问题</h3>
      <QueryState
        pending={messages.isPending || (messages.isFetching && !question)}
        error={messages.error}
        retry={() => void messages.refetch()}
      />
      {question && <p className="user-question">{question.content}</p>}
      {messages.data && !messages.isFetching && !question && (
        <p className="empty-panel">任务输入消息暂不可用，请重新加载会话。</p>
      )}
      {run.result?.kind === "analysis_report" ? (
        <AnalysisReport key={run.id} run={run} />
      ) : (
        <section className="report-placeholder" aria-labelledby="report-title">
          <p className="eyebrow">分析报告</p>
          <h3 id="report-title">
            {run.result?.kind === "simulation_summary"
              ? "模拟执行结果"
              : run.status === "queued"
                ? "任务已保存并排队"
                : "尚无分析报告"}
          </h3>
          <p>
            {run.result?.kind === "simulation_summary"
              ? `后台流程已验证，保存 ${String(run.result.evidence_count)} 条证据。模型调用 0 次，尚未生成分析报告。`
              : !run.execution_available
                ? "此任务来自早期版本，可停止后按原证据重试，以验证当前后台通道。"
                : activeRun(run)
                  ? "后台正在固定证据并分析。关闭或刷新页面不影响任务；停止按钮可请求取消。"
                  : "可核查输入、时间线、原始证据及错误原因，并按原证据重试。"}
          </p>
          {run.result?.coverage_complete === false && (
            <p className="error-message" role="status">
              证据范围不完整。请在输入版本记录和元数据证据中核查缺失文件、日志及采集上限。
            </p>
          )}
          {run.error_message && (
            <p className="error-message">{run.error_message}</p>
          )}
        </section>
      )}
      <RunProgress run={run} />
      {messages.data && messages.data.length > 1 && (
        <details className="conversation-history">
          <summary>会话消息 · {messages.data.length} 条</summary>
          {messages.data.map((item) => (
            <article
              key={item.id}
              className={item.id === run.message_id ? "current-message" : ""}
            >
              <span>
                {item.role === "user" ? "用户" : item.role} · #{item.sequence}
              </span>
              <p>{item.content}</p>
            </article>
          ))}
        </details>
      )}
    </section>
  );
}

function WorkspaceColumns({
  repoId,
  run,
  conversationId,
}: {
  repoId: string;
  run?: Run;
  conversationId?: string;
}) {
  const cache = useQueryClient();
  const [panelView, setPanelView] = useState<{
    conversationId?: string;
    view: "task" | "evidence";
  }>({ view: "task" });
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: () => fetchData<RuntimeInfo>("runtime"),
  });
  const canRead =
    runtime.data?.data_source === "github" ||
    (runtime.data?.data_source === "fixture" &&
      runtime.data.fixture_storage === "database");
  const conversations = useInfiniteQuery({
    queryKey: ["conversations", repoId],
    queryFn: ({ pageParam, signal }) =>
      fetchData<Page<Conversation>>(
        `conversations?repo_id=${encodeURIComponent(repoId)}&limit=50&offset=${pageParam}`,
        { signal },
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: canRead,
  });
  const conversationItems =
    conversations.data?.pages.flatMap((page) => page.items) ?? [];
  const activeId =
    run?.conversation_id ?? conversationId ?? conversationItems[0]?.id;
  const conversation = useQuery({
    queryKey: ["conversation", activeId],
    queryFn: ({ signal }) =>
      fetchData<Conversation>(`conversations/${activeId}`, { signal }),
    enabled: canRead && Boolean(activeId),
  });
  const scopedConversation =
    conversation.data?.repo_id === repoId ? conversation.data : undefined;
  const runs = useInfiniteQuery({
    queryKey: ["runs", repoId, activeId],
    queryFn: ({ pageParam, signal }) =>
      fetchData<Page<Run>>(
        `runs?repo_id=${encodeURIComponent(repoId)}&conversation_id=${activeId}&limit=50&offset=${pageParam}`,
        { signal },
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: canRead && Boolean(scopedConversation),
  });
  const runItems = runs.data?.pages.flatMap((page) => page.items) ?? [];
  const activeRuns = [
    ...new Map(
      [...runItems, ...(run ? [run] : [])]
        .filter(
          (item) =>
            item.repo_id === repoId && item.conversation_id === activeId,
        )
        .map((item) => [item.id, item]),
    ).values(),
  ].sort(
    (left, right) =>
      Date.parse(right.created_at) - Date.parse(left.created_at) ||
      right.id.localeCompare(left.id),
  );
  const latest = scopedConversation ? runs.data?.pages[0]?.items[0] : undefined;
  const latestRun = useQuery<Run>({
    queryKey: ["run", latest?.id],
    queryFn: ({ signal }) => fetchData<Run>(`runs/${latest!.id}`, { signal }),
    initialData: latest,
    initialDataUpdatedAt: 0,
    enabled: canRead && !run && Boolean(latest),
    refetchInterval: (query) =>
      query.state.data && activeRun(query.state.data) ? 3000 : false,
  });
  const selectedRun =
    run ??
    (latestRun.data?.repo_id === repoId &&
    latestRun.data.conversation_id === activeId
      ? latestRun.data
      : undefined);
  const view = panelView.conversationId === activeId ? panelView.view : "task";
  const conversationScroll = useRevealSelection(
    activeId,
    conversationItems.length,
  );
  const historyScroll = useRevealSelection(selectedRun?.id, activeRuns.length);
  const historyError = conversation.error ?? runs.error ?? latestRun.error;
  const historyPending =
    conversations.isPending ||
    (Boolean(activeId) &&
      (conversation.isPending ||
        (Boolean(scopedConversation) && runs.isPending)));
  async function refresh() {
    await Promise.all(
      [
        ["run", selectedRun?.id],
        ["runs", repoId],
        ["conversations", repoId],
        ["conversation", activeId],
        ["messages", activeId],
        ["run-evidence", selectedRun?.id],
        ["run-events", selectedRun?.id],
        ["report", selectedRun?.id],
        ["artifact", repoId],
      ].map((queryKey) => cache.invalidateQueries({ queryKey })),
    );
  }
  return (
    <>
      <div className="workspace-actions">
        <Link
          className="back-link"
          href={`/repositories/${encodeURIComponent(repoId)}`}
        >
          ← 返回仓库并选择新的分析目标
        </Link>
        <button type="button" onClick={() => void refresh()}>
          刷新任务记录
        </button>
      </div>
      <QueryState
        pending={runtime.isPending}
        error={runtime.error}
        retry={() => void runtime.refetch()}
      />
      {runtime.data && !canRead && (
        <div className="empty-panel">
          当前为文件浏览模式，创建会话与任务需要数据库存储。
        </div>
      )}
      {canRead && selectedRun && (
        <div className="workspace-view-tabs" aria-label="工作台内容切换">
          <button
            type="button"
            aria-pressed={view === "task"}
            onClick={() =>
              setPanelView({ conversationId: activeId, view: "task" })
            }
          >
            任务与报告
          </button>
          <button
            type="button"
            aria-pressed={view === "evidence"}
            onClick={() =>
              setPanelView({ conversationId: activeId, view: "evidence" })
            }
          >
            证据
          </button>
        </div>
      )}
      {canRead && (
        <div
          className={`analysis-columns ${selectedRun ? `show-${view}` : ""}`}
        >
          <aside className="conversation-panel" aria-label="会话与任务列表">
            <section
              className="sidebar-section"
              aria-labelledby="conversation-heading"
            >
              <div className="sidebar-section-heading">
                <div className="column-heading">
                  <h2 id="conversation-heading">会话</h2>
                  <span>
                    {conversationItems.length}
                    {conversations.hasNextPage ? "+" : ""}
                  </span>
                </div>
                <p className="history-conversation">选择会话查看历史分析</p>
              </div>
              <div
                className="sidebar-scroll"
                role="region"
                aria-label="会话列表"
                tabIndex={0}
                ref={conversationScroll}
              >
                <QueryState
                  pending={conversations.isPending}
                  error={conversations.error}
                  retry={() => void conversations.refetch()}
                />
                {conversationItems.length === 0 && conversations.isSuccess && (
                  <p className="empty-panel">
                    还没有会话。从仓库的 PR 或 CI 创建第一个任务。
                  </p>
                )}
                <div className="conversation-list">
                  {conversationItems.map((item) => (
                    <Link
                      key={item.id}
                      className={
                        item.id === activeId
                          ? "conversation-item selected"
                          : "conversation-item"
                      }
                      href={`/runs?repo=${encodeURIComponent(repoId)}&conversation=${item.id}`}
                      scroll={false}
                      aria-current={item.id === activeId ? "true" : undefined}
                    >
                      <strong>{item.title}</strong>
                      <span>{date(item.created_at)}</span>
                    </Link>
                  ))}
                </div>
                {conversations.hasNextPage && (
                  <button
                    type="button"
                    className="sidebar-load-more"
                    disabled={conversations.isFetchingNextPage}
                    onClick={() => void conversations.fetchNextPage()}
                  >
                    {conversations.isFetchingNextPage
                      ? "正在加载…"
                      : "加载更多会话"}
                  </button>
                )}
              </div>
            </section>
            <section
              className="sidebar-section history-section"
              aria-labelledby="history-heading"
            >
              <div className="sidebar-section-heading">
                <div className="column-heading">
                  <h2 id="history-heading">历史任务</h2>
                  <span>
                    {activeRuns.length}
                    {runs.hasNextPage ? "+" : ""}
                  </span>
                </div>
                <p
                  className="history-conversation"
                  title={scopedConversation?.title}
                >
                  {scopedConversation?.title ?? "选择会话后查看历史任务"}
                </p>
              </div>
              <div
                className="sidebar-scroll"
                role="region"
                aria-label="历史任务列表"
                tabIndex={0}
                ref={historyScroll}
              >
                <QueryState
                  pending={Boolean(activeId) && conversation.isPending}
                  error={conversation.error}
                  retry={() => void conversation.refetch()}
                />
                {conversation.data && !scopedConversation && (
                  <p className="error-message" role="alert">
                    所选会话不属于当前仓库。
                  </p>
                )}
                <QueryState
                  pending={Boolean(scopedConversation) && runs.isPending}
                  error={runs.error}
                  retry={() => void runs.refetch()}
                />
                <QueryState
                  pending={false}
                  error={run ? null : latestRun.error}
                  retry={() => void latestRun.refetch()}
                />
                <div className="run-list">
                  {activeRuns.map((item) => (
                    <Link
                      key={item.id}
                      href={`/runs/${item.id}`}
                      scroll={false}
                      className={
                        item.id === selectedRun?.id
                          ? "run-item selected"
                          : "run-item"
                      }
                      aria-current={
                        item.id === selectedRun?.id ? "true" : undefined
                      }
                    >
                      <span>
                        {taskName[item.task_type]}{" "}
                        {item.target_id && `#${item.target_id}`}
                      </span>
                      <small>
                        {runStatus[item.status]} · {date(item.created_at)} ·{" "}
                        {item.id.slice(0, 8)}
                      </small>
                    </Link>
                  ))}
                </div>
                {runs.isSuccess && !runs.error && activeRuns.length === 0 && (
                  <p className="column-intro">该会话暂无分析任务。</p>
                )}
                {runs.hasNextPage && (
                  <button
                    type="button"
                    className="sidebar-load-more"
                    disabled={runs.isFetchingNextPage}
                    onClick={() => void runs.fetchNextPage()}
                  >
                    {runs.isFetchingNextPage ? "正在加载…" : "加载更多任务记录"}
                  </button>
                )}
              </div>
            </section>
          </aside>
          {selectedRun ? (
            <TaskContent key={`content-${selectedRun.id}`} run={selectedRun} />
          ) : (
            <section className="task-content workspace-empty">
              <span className="empty-symbol">⑂</span>
              <h2>
                {historyError
                  ? "历史记录暂不可用"
                  : historyPending
                    ? "正在加载会话记录"
                    : scopedConversation
                      ? "该会话暂无分析任务"
                      : "选择会话，回看历史分析"}
              </h2>
              <QueryState
                pending={historyPending}
                error={historyError}
                retry={() => void refresh()}
              />
              {!historyPending && !historyError && (
                <p>
                  选择会话会自动展示最近一次分析，也可以从左侧打开历史任务。
                </p>
              )}
              <Link
                className="primary-link"
                href={`/repositories/${encodeURIComponent(repoId)}`}
              >
                选择 PR 或 CI →
              </Link>
            </section>
          )}
          {selectedRun ? (
            <EvidencePanel
              key={`evidence-${selectedRun.id}`}
              run={selectedRun}
            />
          ) : (
            <aside className="evidence-panel">
              <div className="column-heading">
                <h2>证据</h2>
              </div>
              <p className="column-intro">
                选择任务后显示它保存的代码、日志和版本。
              </p>
            </aside>
          )}
        </div>
      )}
    </>
  );
}

export function RunDetail({ runId }: { runId: string }) {
  const run = useQuery<Run>({
    queryKey: ["run", runId],
    refetchInterval: (query) =>
      query.state.data && activeRun(query.state.data) ? 3000 : false,
    queryFn: ({ signal }) => fetchData<Run>(`runs/${runId}`, { signal }),
  });
  return (
    <div className="main-content analysis-main">
      <div className="page-heading">
        <div>
          <p className="eyebrow">分析工作台</p>
          <h1>任务与证据</h1>
          <p className="intro">按创建时保存的版本回看每一次分析。</p>
        </div>
        <span className="step-badge">第 16 / 24 步 · v0.1</span>
      </div>
      <QueryState
        pending={run.isPending}
        error={run.error}
        retry={() => void run.refetch()}
      />
      {run.data && (
        <WorkspaceColumns
          key={run.data.repo_id}
          repoId={run.data.repo_id}
          run={run.data}
        />
      )}
      <Link className="text-link" href="/runs">
        查看其他仓库的会话 →
      </Link>
    </div>
  );
}

export function RunIndex({
  repoId,
  conversationId,
}: {
  repoId?: string;
  conversationId?: string;
}) {
  const router = useRouter();
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: ({ signal }) =>
      fetchData<Collection<Repository>>("repositories", { signal }),
  });
  const selected = repoId ?? repositories.data?.items[0]?.id;
  const exists = repositories.data?.items.some((item) => item.id === selected);
  return (
    <div className="main-content analysis-main">
      <div className="page-heading">
        <div>
          <p className="eyebrow">分析工作台</p>
          <h1>会话与任务</h1>
          <p className="intro">打开历史任务，核查保存的输入和证据。</p>
        </div>
        <span className="step-badge">第 16 / 24 步 · v0.1</span>
      </div>
      <QueryState
        pending={repositories.isPending}
        error={repositories.error}
        retry={() => void repositories.refetch()}
      />
      {repositories.data && repositories.data.items.length === 0 && (
        <p className="empty-panel">暂无可用仓库。</p>
      )}
      {repositories.data && (
        <label className="repository-picker">
          当前仓库
          <select
            value={selected ?? ""}
            onChange={(event) =>
              router.push(
                `/runs?repo=${encodeURIComponent(event.target.value)}`,
              )
            }
          >
            {repoId && !exists && <option value={repoId}>仓库不存在</option>}
            {repositories.data.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.full_name}
              </option>
            ))}
          </select>
        </label>
      )}
      {selected && exists && (
        <WorkspaceColumns
          key={selected}
          repoId={selected}
          conversationId={conversationId}
        />
      )}
      {repositories.data && selected && !exists && (
        <p className="empty-panel">该仓库不存在或尚未导入。</p>
      )}
    </div>
  );
}
