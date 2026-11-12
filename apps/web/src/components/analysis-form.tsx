// 文件用途：统一分析表单和会话输入框，保留幂等提交、未知结果与文件模式处理。
"use client";
import Link from "next/link";
import { useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ApiError, fetchData, postData } from "@/lib/api-client";
import type {
  Collection,
  PullRequestSummary,
  CIRunSummary,
  RuntimeInfo,
} from "@/lib/repositories";
import type { AnalysisType, Conversation, Page, Run } from "@/lib/workflows";
import { taskName } from "@/lib/workflows";
import { RunSubmission } from "@/lib/run-submission";
import { QueryState } from "@/components/query-state";
import { Icon } from "@/components/icon";

export function AnalysisForm({
  repoId,
  taskType: fixedType,
  targetId: fixedTarget,
  composer = false,
  initialConversationId,
  initialTaskType,
  initialTargetId,
}: {
  repoId: string;
  taskType?: AnalysisType;
  targetId?: string;
  composer?: boolean;
  initialConversationId?: string;
  initialTaskType?: AnalysisType;
  initialTargetId?: string;
}) {
  const router = useRouter();
  const cache = useQueryClient();
  const fieldId = useId();
  const [choice, setChoice] = useState(
    initialTaskType ? `${initialTaskType}:${initialTargetId ?? ""}` : "",
  );
  const taskType =
    fixedType ?? ((choice.split(":")[0] as AnalysisType) || "knowledge_qa");
  const targetId = fixedTarget ?? (choice.split(":")[1] || undefined);
  const [question, setQuestion] = useState(
    composer
      ? ""
      : taskType === "pr_review"
        ? "请审查这个 PR 的风险，并说明可核查的证据。"
        : taskType === "ci_debug"
          ? "请分析这次 CI 失败的原因，并列出验证步骤。"
          : "项目对任务所有者隔离和 labels=null 有什么约束？请引用资料。",
  );
  const [useKnowledge, setUseKnowledge] = useState(true);
  const [conversationId, setConversationId] = useState(
    initialConversationId ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [conflict, setConflict] = useState(false);
  const locked = useRef(false);
  const submission = useRef(new RunSubmission());
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: () => fetchData<RuntimeInfo>("runtime"),
  });
  const available =
    runtime.data?.data_source === "github" ||
    runtime.data?.fixture_storage === "database";
  const conversations = useInfiniteQuery({
    queryKey: ["conversations", repoId],
    queryFn: ({ pageParam, signal }) =>
      fetchData<Page<Conversation>>(
        `conversations?repo_id=${encodeURIComponent(repoId)}&limit=50&offset=${pageParam}`,
        { signal },
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: available && (!composer || uncertain),
  });
  const prs = useQuery({
    queryKey: ["pull-requests", repoId],
    queryFn: ({ signal }) =>
      fetchData<Collection<PullRequestSummary>>(
        `repositories/${encodeURIComponent(repoId)}/pull-requests`,
        { signal },
      ),
    enabled: available && composer,
  });
  const ci = useQuery({
    queryKey: ["ci-runs", repoId],
    queryFn: ({ signal }) =>
      fetchData<Collection<CIRunSummary>>(
        `repositories/${encodeURIComponent(repoId)}/ci-runs`,
        { signal },
      ),
    enabled: available && composer,
  });
  const options = conversations.data?.pages.flatMap((p) => p.items) ?? [];
  const targets = [
    ...(prs.data?.items.map((pr) => ({
      value: `pr_review:${pr.number}`,
      label: `PR #${pr.number} · ${pr.title}`,
    })) ?? []),
    ...(ci.data?.items.map((run) => ({
      value: `ci_debug:${run.id}`,
      label: `CI #${run.id} · ${run.name}`,
    })) ?? []),
    { value: "knowledge_qa:", label: "项目知识问答" },
  ];
  const disabled =
    busy ||
    !question.trim() ||
    conflict ||
    (uncertain && !conversationId) ||
    (composer && !choice);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked.current || !available || disabled) return;
    locked.current = true;
    setBusy(true);
    setError(null);
    let id = conversationId;
    try {
      if (!id) {
        try {
          const created = await postData<Conversation>("conversations", {
            repo_id: repoId,
            title: question.trim().slice(0, 60),
          });
          id = created.id;
          setConversationId(id);
          void cache.invalidateQueries({ queryKey: ["conversations", repoId] });
        } catch (cause) {
          if (
            !(cause instanceof ApiError) ||
            cause.status === 0 ||
            cause.status >= 500
          )
            setUncertain(true);
          throw cause;
        }
      }
      const run = await submission.current.submit(
        {
          repo_id: repoId,
          conversation_id: id,
          task_type: taskType,
          target_id: targetId,
          question: question.trim(),
          use_knowledge: useKnowledge,
        },
        (data, key) => postData<Run>("runs", data, key),
      );
      await cache.invalidateQueries({ queryKey: ["runs", repoId] });
      void cache.invalidateQueries({ queryKey: ["messages", id] });
      submission.current = new RunSubmission();
      if (composer) setQuestion("");
      router.push(`/runs/${run.id}`, { scroll: false });
    } catch (cause) {
      setError(
        cause instanceof Error ? cause : new Error("任务创建失败，请重试"),
      );
      if (cause instanceof ApiError && cause.status === 409) setConflict(true);
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      className={composer ? "analysis-composer" : "analysis-create"}
      aria-label={composer ? "分析指令输入" : "开始分析"}
    >
      {!composer && (
        <div className="analysis-create-heading">
          <h2>
            {taskName[taskType]} {targetId && `#${targetId}`}
          </h2>
          <Link
            className="text-link"
            href={`/runs?repo=${encodeURIComponent(repoId)}`}
          >
            打开分析工作台 ↗
          </Link>
        </div>
      )}
      <QueryState
        pending={runtime.isPending}
        error={runtime.error}
        retry={() => void runtime.refetch()}
      />
      {runtime.data && !available && (
        <p className="empty-panel">
          当前为文件浏览模式，切换到数据库模式后可创建分析任务。
        </p>
      )}
      {available && (
        <form onSubmit={(event) => void submit(event)}>
          {(!composer || uncertain) && (
            <div className="conversation-select">
              <QueryState
                pending={conversations.isPending}
                error={conversations.error}
                retry={() => void conversations.refetch()}
              />
              <label htmlFor={`${fieldId}-conversation`}>保存到会话</label>
              <select
                id={`${fieldId}-conversation`}
                value={conversationId}
                disabled={busy}
                onChange={(event) => {
                  setConversationId(event.target.value);
                  setError(null);
                  setConflict(false);
                }}
              >
                <option value="">新建会话</option>
                {conversationId &&
                  !options.some((item) => item.id === conversationId) && (
                    <option value={conversationId}>当前会话</option>
                  )}
                {options.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
              {conversations.hasNextPage && (
                <button
                  type="button"
                  className="text-button"
                  disabled={conversations.isFetchingNextPage}
                  onClick={() => void conversations.fetchNextPage()}
                >
                  加载更多会话
                </button>
              )}
            </div>
          )}
          {uncertain && (
            <p className="error-message" role="alert">
              会话创建结果未知，请先刷新并选择已创建的会话。
              <button
                type="button"
                onClick={() => void conversations.refetch()}
              >
                刷新会话列表
              </button>
            </p>
          )}
          <label
            className={composer ? "sr-only" : ""}
            htmlFor={`${fieldId}-question`}
          >
            分析问题
          </label>
          <textarea
            id={`${fieldId}-question`}
            value={question}
            disabled={busy}
            maxLength={20000}
            required
            rows={composer ? 2 : 3}
            placeholder={
              initialConversationId
                ? "继续提问或输入新的分析指令…"
                : "输入你的分析指令…"
            }
            onChange={(event) => {
              setQuestion(event.target.value);
              setError(null);
              setConflict(false);
            }}
          />
          {error && (
            <div className="error-message" role="alert">
              <p>{error.message}</p>
              {error instanceof ApiError && (
                <p className="request-detail">
                  {error.code}
                  {error.requestId && ` · 请求 ${error.requestId}`}
                </p>
              )}
              {conflict && <p>请核对任务和会话，修改输入后重新提交。</p>}
            </div>
          )}
          <div className="composer-controls">
            {composer && (
              <select
                aria-label="分析目标"
                value={choice}
                disabled={busy}
                onChange={(e) => {
                  setChoice(e.target.value);
                  setConflict(false);
                  setError(null);
                }}
              >
                <option value="" disabled>
                  选择 PR / CI 或知识问答
                </option>
                {choice && !targets.some((t) => t.value === choice) && (
                  <option value={choice}>
                    {taskName[taskType]} {targetId && `#${targetId}`}
                  </option>
                )}
                {targets.map((t) => (
                  <option value={t.value} key={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            )}
            {taskType !== "knowledge_qa" && (
              <label className="knowledge-toggle">
                <input
                  type="checkbox"
                  checked={useKnowledge}
                  disabled={busy}
                  onChange={(e) => setUseKnowledge(e.target.checked)}
                />
                <Icon name="book" size={16} />
                项目资料
              </label>
            )}
            <button
              className={composer ? "send-button" : "primary-button"}
              type="submit"
              disabled={disabled}
              aria-label={
                busy ? "正在保存" : error ? "重试创建任务" : "发送分析指令"
              }
            >
              {composer ? (
                busy ? (
                  <span className="spinner" />
                ) : (
                  <Icon name="up" size={20} />
                )
              ) : busy ? (
                "正在保存…"
              ) : error ? (
                "重试创建任务"
              ) : (
                "开始分析 →"
              )}
            </button>
          </div>
          {composer && (prs.error || ci.error) && (
            <QueryState
              pending={false}
              error={prs.error ?? ci.error}
              retry={() => {
                void prs.refetch();
                void ci.refetch();
              }}
            />
          )}
          <p className="composer-hint">
            {runtime.data?.model.provider === "fake"
              ? "离线演示 · 分析结果可通过引用核查"
              : "分析结果可通过引用核查 · 发送指令会产生模型 API 用量"}
          </p>
        </form>
      )}
    </section>
  );
}
