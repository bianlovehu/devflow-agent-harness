// 文件用途：按会话展示指令与分析时间线，支持指令目录跳转和固定版本证据抽屉。
"use client";
import Link from "next/link";
import {
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchData } from "@/lib/api-client";
import type {
  ArtifactContent,
  Conversation,
  Evidence,
  Message,
  Page,
  Run,
} from "@/lib/workflows";
import { readMessages, runStatus, taskName } from "@/lib/workflows";
import { activeRun, RunControls, RunProgress } from "@/components/run-progress";
import { QueryState } from "@/components/query-state";
import { AnalysisReport } from "@/components/analysis-report";
import { AnalysisForm } from "@/components/analysis-form";
import { RunCost } from "@/components/budget-summary";
import { useWorkspace } from "@/components/workspace-context";
import { DevFlowMark, Icon } from "@/components/icon";
import {
  EvidenceNavigation,
  type EvidenceLocation,
} from "@/components/evidence-navigation";

function subscribeNarrow(listener: () => void) {
  const query = window.matchMedia("(max-width: 1100px)");
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}
const narrowSnapshot = () => window.matchMedia("(max-width: 1100px)").matches;

function date(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
function versionOf(run: Run) {
  const resources = run.input_version.resources;
  if (!Array.isArray(resources)) return "未记录版本";
  return (
    resources
      .map((item) =>
        String(item.head_sha ?? item.version ?? item.content_sha256 ?? ""),
      )
      .filter(Boolean)
      .join(" · ") || "见输入版本记录"
  );
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

function EvidencePanel({
  run,
  location,
  onClose,
}: {
  run: Run;
  location: EvidenceLocation;
  onClose: () => void;
}) {
  const [selectedId, setSelectedId] = useState(location.evidenceId ?? "");
  const evidence = useQuery({
    queryKey: ["run-evidence", run.id],
    refetchInterval: activeRun(run) ? 3000 : false,
    queryFn: ({ signal }) =>
      fetchData<Page<Evidence>>(`runs/${run.id}/evidence`, { signal }),
  });
  const selected = selectedId
    ? evidence.data?.items.find((item) => item.id === selectedId)
    : evidence.data?.items[0];
  const artifact = useQuery({
    queryKey: ["artifact", run.repo_id, selected?.artifact_id],
    queryFn: ({ signal }) =>
      fetchData<ArtifactContent>(
        `artifacts/${selected!.artifact_id}?repo_id=${encodeURIComponent(run.repo_id)}`,
        { signal },
      ),
    enabled: Boolean(selected),
  });
  const selectedRange =
    selected && selected.id === location.evidenceId
      ? {
          start: location.start ?? selected.start_line,
          end: location.end ?? selected.end_line,
        }
      : { start: selected?.start_line ?? 1, end: selected?.end_line ?? 1 };
  return (
    <aside className="evidence-panel" aria-label="固定版本证据">
      <div className="column-heading">
        <h2>证据</h2>
        <button className="text-button" onClick={onClose}>
          指令目录
        </button>
        <span>{evidence.data?.items.length ?? 0} 条</span>
        <button
          className="icon-button"
          aria-label="关闭证据面板"
          onClick={onClose}
        >
          <Icon name="close" size={18} />
        </button>
      </div>
      <p className="column-intro">任务固定的原始版本；采集完成后可查</p>
      <QueryState
        pending={evidence.isPending}
        error={evidence.error}
        retry={() => void evidence.refetch()}
      />
      {selectedId && evidence.isSuccess && !selected && (
        <p className="error-message" role="alert">
          引用的证据暂不可用，请刷新或切换证据来源。
        </p>
      )}
      {evidence.data?.items.length === 0 && (
        <div className="empty-panel">此任务尚无证据。</div>
      )}
      <details className="evidence-sources">
        <summary>切换证据来源</summary>
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
                · L{item.start_line}–{item.end_line} ·{" "}
                {item.version.slice(0, 8)}
              </span>
            </button>
          ))}
        </div>
      </details>
      {selected && (
        <section className="evidence-preview" key={selected.id}>
          <h3>{selected.path}</h3>
          <p className="evidence-location">
            第 {selectedRange.start}–{selectedRange.end} 行
          </p>
          <details className="evidence-version-details">
            <summary>版本与保存信息 · {selected.version.slice(0, 8)}</summary>
            <p className="hash-note">
              证据 ID <code>{selected.id}</code>
            </p>
            <p className="evidence-location">
              保存范围：第 {selected.start_line}–{selected.end_line} 行
            </p>
            <dl className="version-facts">
              <dt>固定版本</dt>
              <dd>
                <code>{selected.version}</code>
              </dd>
              <dt>保存时间</dt>
              <dd>{date(selected.retrieved_at)}</dd>
            </dl>
          </details>
          <QueryState
            pending={artifact.isPending}
            error={artifact.error}
            retry={() => void artifact.refetch()}
          />
          {artifact.data && (
            <>
              <SourceLines
                content={artifact.data.content}
                start={selectedRange.start}
                end={selectedRange.end}
              />
              <details className="artifact-full">
                <summary>查看完整原文</summary>
                <SourceLines
                  content={artifact.data.content}
                  start={selectedRange.start}
                  end={selectedRange.end}
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
  const openEvidence = useContext(EvidenceNavigation);
  return (
    <article
      className="run-response"
      aria-label={`${taskName[run.task_type]}分析结果`}
    >
      <div className="response-heading">
        <span className="assistant-avatar">
          <DevFlowMark size={22} />
        </span>
        <strong>DevFlow</strong>
        <span className={`run-status status-${run.status}`}>
          {runStatus[run.status]}
        </span>
        <span className="response-target">
          {taskName[run.task_type]} {run.target_id && `#${run.target_id}`}
        </span>
      </div>
      {run.result?.kind === "analysis_report" ? (
        <AnalysisReport key={run.id} run={run} />
      ) : (
        <section className="report-placeholder">
          <h3>
            {run.result?.kind === "simulation_summary"
              ? "模拟执行结果"
              : run.status === "queued"
                ? "任务已保存并排队"
                : activeRun(run)
                  ? "正在分析…"
                  : "尚无分析报告"}
          </h3>
          <p>
            {run.result?.kind === "simulation_summary"
              ? `后台流程已验证，保存 ${String(run.result.evidence_count)} 条证据，未调用模型。`
              : !run.execution_available
                ? "这是早期版本任务，可按原证据重试。"
                : activeRun(run)
                  ? "正在固定证据并分析，关闭页面不影响任务执行。"
                  : "可查看执行详情、原始证据及错误原因，并按原证据重试。"}
          </p>
          {run.result?.coverage_complete === false && (
            <p className="error-message">
              证据范围不完整，请查看输入版本及采集范围。
            </p>
          )}
          {run.error_message && (
            <p className="error-message">{run.error_message}</p>
          )}
        </section>
      )}
      <div className="response-actions">
        <button type="button" onClick={() => openEvidence?.({ runId: run.id })}>
          <Icon name="file" size={16} />
          查看证据
        </button>
        <RunControls run={run} />
        <time dateTime={run.created_at}>{date(run.created_at)}</time>
      </div>
      <details className="run-metadata">
        <summary>版本与执行详情</summary>
        <p className="task-id">任务 {run.id}</p>
        <p className="hash-note">分析依据：{versionOf(run)}</p>
        <details>
          <summary>输入版本记录</summary>
          <pre>{JSON.stringify(run.input_version, null, 2)}</pre>
        </details>
        <RunCost runId={run.id} />
        <RunProgress run={run} />
      </details>
    </article>
  );
}

async function readRuns(
  repoId: string,
  conversationId: string,
  signal?: AbortSignal,
) {
  const items: Run[] = [];
  let offset: number | null = 0;
  while (offset !== null) {
    const page: Page<Run> = await fetchData(
      `runs?repo_id=${encodeURIComponent(repoId)}&conversation_id=${encodeURIComponent(conversationId)}&limit=100&offset=${offset}`,
      { signal },
    );
    items.push(...page.items);
    offset = page.next_offset ?? null;
  }
  return items;
}

function ConversationWorkspace({
  repoId,
  conversationId,
  focusedRun,
}: {
  repoId: string;
  conversationId?: string;
  focusedRun?: Run;
}) {
  const { available, runtime, repository } = useWorkspace();
  const cache = useQueryClient();
  const viewport = useRef<HTMLDivElement>(null);
  const [activeMessage, setActiveMessage] = useState(
    focusedRun?.message_id ?? "",
  );
  const narrow = useSyncExternalStore(
    subscribeNarrow,
    narrowSnapshot,
    () => false,
  );
  const [panelChoice, setPanel] = useState<"outline" | "evidence" | null>();
  const panel =
    panelChoice === undefined ? (narrow ? null : "outline") : panelChoice;
  const [location, setLocation] = useState<EvidenceLocation | null>(null);
  const conversation = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: ({ signal }) =>
      fetchData<Conversation>(`conversations/${conversationId}`, { signal }),
    enabled: available && Boolean(conversationId),
  });
  const scoped =
    conversation.data?.repo_id === repoId ? conversation.data : undefined;
  const runs = useQuery({
    queryKey: ["runs", repoId, conversationId, "timeline"],
    queryFn: ({ signal }) => readRuns(repoId, conversationId!, signal),
    enabled: available && Boolean(scoped),
    refetchInterval: (query) =>
      query.state.data?.some(activeRun) ? 3000 : false,
  });
  const messages = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: ({ signal }) => readMessages(conversationId!, signal),
    enabled: available && Boolean(scoped),
  });
  const runItems = [
    ...new Map(
      [...(runs.data ?? []), ...(focusedRun ? [focusedRun] : [])]
        .filter(
          (r) => r.repo_id === repoId && r.conversation_id === conversationId,
        )
        .map((r) => [r.id, r]),
    ).values(),
  ].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const instructions = (messages.data ?? [])
    .filter((m) => m.role === "user")
    .sort((a, b) => a.sequence - b.sequence);
  const lastRun = runItems.at(-1);
  const evidenceRun = runItems.find((r) => r.id === location?.runId);
  const loading =
    Boolean(conversationId) &&
    (conversation.isPending ||
      (Boolean(scoped) && (runs.isPending || messages.isPending)));
  const error = conversation.error ?? runs.error ?? messages.error;
  const wrongRepository = conversation.data && !scoped;

  useEffect(() => {
    if (!focusedRun?.message_id || !messages.data?.length) return;
    const frame = requestAnimationFrame(() =>
      document
        .getElementById(`instruction-${focusedRun.message_id}`)
        ?.scrollIntoView({ block: "start" }),
    );
    return () => cancelAnimationFrame(frame);
  }, [focusedRun?.message_id, messages.data?.length]);
  useEffect(() => {
    const area = viewport.current;
    if (!area || !instructions.length) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const top = area.getBoundingClientRect().top + 140;
        const turns = [
          ...area.querySelectorAll<HTMLElement>(".conversation-turn"),
        ];
        const current =
          area.scrollTop + area.clientHeight >= area.scrollHeight - 8
            ? turns.at(-1)
            : (turns
                .filter((item) => item.getBoundingClientRect().top <= top)
                .at(-1) ?? turns[0]);
        if (current) setActiveMessage(current.dataset.messageId ?? "");
      });
    };
    area.addEventListener("scroll", update, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      area.removeEventListener("scroll", update);
    };
  }, [instructions.length]);
  useEffect(() => {
    if (panel !== "evidence") return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPanel(narrow ? null : "outline");
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [panel, narrow]);
  function jump(message: Message) {
    setActiveMessage(message.id);
    document.getElementById(`instruction-${message.id}`)?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "start",
    });
  }
  async function refresh() {
    await Promise.all(
      [
        ["runs", repoId],
        ["conversation", conversationId],
        ["messages", conversationId],
        ["run-evidence"],
        ["report"],
      ].map((queryKey) => cache.invalidateQueries({ queryKey })),
    );
  }
  const composer = (
    <AnalysisForm
      key={`${repoId}:${conversationId ?? "new"}`}
      repoId={repoId}
      composer
      initialConversationId={scoped?.id}
      initialTaskType={lastRun?.task_type}
      initialTargetId={lastRun?.target_id ?? undefined}
    />
  );
  return (
    <EvidenceNavigation.Provider
      value={(next) => {
        setLocation(next);
        setPanel("evidence");
      }}
    >
      <div
        className={`chat-workspace ${panel && instructions.length ? `with-${panel}` : ""}`}
      >
        <section className="chat-pane" aria-label="会话内容">
          {conversationId && (
            <div className="chat-toolbar">
              <span>{instructions.length} 条指令</span>
              <button
                className="icon-button"
                aria-label="刷新会话"
                disabled={runs.isFetching}
                onClick={() => void refresh()}
              >
                <Icon name="refresh" size={18} />
              </button>
              <button
                className="icon-button"
                aria-label={
                  panel === "outline" ? "收起指令目录" : "展开指令目录"
                }
                aria-pressed={panel === "outline"}
                onClick={() => setPanel(panel === "outline" ? null : "outline")}
              >
                <Icon name="list" size={19} />
              </button>
            </div>
          )}
          <div className="conversation-scroll" ref={viewport}>
            <QueryState
              pending={loading || runtime.isPending}
              error={error ?? runtime.error}
              retry={() => void refresh()}
            />
            {wrongRepository && (
              <p className="empty-panel">
                该会话不属于当前仓库，请从左侧重新选择。
              </p>
            )}
            {!conversationId ? (
              <div className="chat-welcome">
                <DevFlowMark size={48} />
                <h1>今天想分析什么？</h1>
                <p>在当前仓库中审查 PR、排查 CI，或查询项目资料</p>
                {composer}
                <p className="welcome-repository">
                  当前仓库：{repository?.full_name ?? repoId}
                </p>
                <div className="welcome-suggestions">
                  <Link
                    href={`/repositories/${encodeURIComponent(repoId)}?tab=prs`}
                  >
                    <Icon name="repo" size={18} />
                    审查 PR 风险
                  </Link>
                  <Link
                    href={`/repositories/${encodeURIComponent(repoId)}?tab=ci`}
                  >
                    <Icon name="refresh" size={18} />
                    排查 CI 失败
                  </Link>
                  <Link href={`/knowledge?repo=${encodeURIComponent(repoId)}`}>
                    <Icon name="book" size={18} />
                    查询项目规范
                  </Link>
                </div>
              </div>
            ) : (
              <div className="conversation-reading">
                {!loading && scoped && !instructions.length && (
                  <div className="conversation-empty">
                    <DevFlowMark size={32} />
                    <h2>开始这个会话的第一次分析</h2>
                    <p>选择分析目标，输入你的问题。</p>
                  </div>
                )}
                {instructions.map((message) => (
                  <section
                    className="conversation-turn"
                    id={`instruction-${message.id}`}
                    data-message-id={message.id}
                    key={message.id}
                  >
                    <div className="user-message">
                      <p>{message.content}</p>
                      <time dateTime={message.created_at}>
                        {date(message.created_at)}
                      </time>
                    </div>
                    {runItems
                      .filter((r) => r.message_id === message.id)
                      .map((run) => (
                        <TaskContent run={run} key={run.id} />
                      ))}
                    {!loading &&
                      !runItems.some((r) => r.message_id === message.id) && (
                        <p className="column-intro">
                          此条指令尚无关联分析结果。
                        </p>
                      )}
                  </section>
                ))}
              </div>
            )}
          </div>
          {conversationId && scoped && !loading && (
            <div className="chat-composer-footer">{composer}</div>
          )}
        </section>
        {panel === "outline" && instructions.length > 0 && (
          <aside className="instruction-directory" aria-label="指令目录">
            <div className="directory-heading">
              <h2>指令目录</h2>
              <span>{instructions.length} 条指令</span>
              <button
                className="icon-button"
                aria-label="收起指令目录"
                onClick={() => setPanel(null)}
              >
                <Icon name="close" size={16} />
              </button>
            </div>
            <nav>
              {instructions.map((message) => (
                <button
                  type="button"
                  key={message.id}
                  className={
                    message.id === (activeMessage || instructions[0]?.id)
                      ? "active"
                      : ""
                  }
                  aria-current={
                    message.id === (activeMessage || instructions[0]?.id)
                      ? "location"
                      : undefined
                  }
                  onClick={() => jump(message)}
                  title={message.content}
                >
                  {message.content}
                </button>
              ))}
            </nav>
          </aside>
        )}
        {panel === "evidence" && evidenceRun && location && (
          <EvidencePanel
            key={`${location.runId}:${location.evidenceId ?? ""}:${location.start ?? ""}`}
            run={evidenceRun}
            location={location}
            onClose={() => setPanel(narrow ? null : "outline")}
          />
        )}
      </div>
    </EvidenceNavigation.Provider>
  );
}

export function RunDetail({ runId }: { runId: string }) {
  const run = useQuery<Run>({
    queryKey: ["run", runId],
    queryFn: ({ signal }) => fetchData<Run>(`runs/${runId}`, { signal }),
    refetchInterval: (query) =>
      query.state.data && activeRun(query.state.data) ? 3000 : false,
  });
  return (
    <>
      <QueryState
        pending={run.isPending}
        error={run.error}
        retry={() => void run.refetch()}
      />
      {run.data && (
        <ConversationWorkspace
          key={run.data.conversation_id}
          repoId={run.data.repo_id}
          conversationId={run.data.conversation_id}
          focusedRun={run.data}
        />
      )}
    </>
  );
}
export function RunIndex({
  repoId: initialRepo,
  conversationId,
}: {
  repoId?: string;
  conversationId?: string;
}) {
  const { repoId, repositories } = useWorkspace();
  const selected = initialRepo ?? repoId;
  const exists = repositories.data?.items.some((repo) => repo.id === selected);
  return (
    <>
      <QueryState
        pending={repositories.isPending}
        error={repositories.error}
        retry={() => void repositories.refetch()}
      />
      {selected && exists && (
        <ConversationWorkspace
          key={conversationId ?? selected}
          repoId={selected}
          conversationId={conversationId}
        />
      )}
      {repositories.data && !exists && (
        <div className="management-page">
          <p className="empty-panel">暂无可用仓库，请先添加仓库。</p>
          <Link className="primary-link" href="/repositories">
            打开仓库 →
          </Link>
        </div>
      )}
    </>
  );
}
