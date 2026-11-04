// 文件用途：从 PR 或 CI 创建会话与分析任务，并处理重试和文件模式限制。
"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ApiError, fetchData, postData } from "@/lib/api-client";
import type { RuntimeInfo } from "@/lib/repositories";
import type { AnalysisType, Conversation, Page, Run } from "@/lib/workflows";
import { taskName } from "@/lib/workflows";
import { RunSubmission } from "@/lib/run-submission";
import { QueryState } from "@/components/query-state";

export function AnalysisForm({
  repoId,
  taskType,
  targetId,
}: {
  repoId: string;
  taskType: AnalysisType;
  targetId?: string;
}) {
  const router = useRouter();
  const cache = useQueryClient();
  const [question, setQuestion] = useState(
    taskType === "pr_review"
      ? "请审查这个 PR 的风险，并说明可核查的证据。"
      : taskType === "ci_debug"
        ? "请分析这次 CI 失败的原因，并列出验证步骤。"
        : "项目对任务所有者隔离和 labels=null 有什么约束？请引用资料。",
  );
  const [useKnowledge, setUseKnowledge] = useState(true);
  const [conversationId, setConversationId] = useState("");
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
    enabled: available,
  });
  const options = conversations.data?.pages.flatMap((page) => page.items) ?? [];

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      locked.current ||
      !available ||
      !question.trim() ||
      conflict ||
      (uncertain && !conversationId)
    )
      return;
    locked.current = true;
    setBusy(true);
    setError(null);
    let id = conversationId;
    try {
      if (!id) {
        try {
          const created = await postData<Conversation>("conversations", {
            repo_id: repoId,
            title: `${taskName[taskType]}${targetId ? ` #${targetId}` : ""}`,
          });
          id = created.id;
          setConversationId(id);
          cache.invalidateQueries({ queryKey: ["conversations", repoId] });
        } catch (cause) {
          // 会话创建不支持幂等；结果未知时先核对列表，避免自动再创建一次。
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
      router.push(`/runs/${run.id}`);
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
    <section className="analysis-create" aria-labelledby="analysis-title">
      <div className="analysis-create-heading">
        <div>
          <p className="eyebrow">开始分析</p>
          <h2 id="analysis-title">
            {taskName[taskType]} {targetId && `#${targetId}`}
          </h2>
        </div>
        <Link
          className="text-link"
          href={`/runs?repo=${encodeURIComponent(repoId)}`}
        >
          查看会话与任务 →
        </Link>
      </div>
      <QueryState
        pending={runtime.isPending}
        error={runtime.error}
        retry={() => void runtime.refetch()}
      />
      {runtime.data && !available && (
        <p className="empty-panel">
          {runtime.data.data_source === "fixture" &&
          runtime.data.fixture_storage === "files"
            ? "当前为文件浏览模式。请切换到数据库模式后创建任务。"
            : "当前模式暂不支持创建任务。"}
        </p>
      )}
      {available && (
        <form onSubmit={(event) => void submit(event)}>
          <QueryState
            pending={conversations.isPending}
            error={conversations.error}
            retry={() => void conversations.refetch()}
          />
          <label htmlFor="conversation">保存到会话</label>
          <select
            id="conversation"
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
                <option value={conversationId}>本次新建的会话</option>
              )}
            {options.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} · {item.id.slice(0, 8)}
              </option>
            ))}
          </select>
          {conversations.hasNextPage && (
            <button
              type="button"
              className="text-link"
              disabled={conversations.isFetchingNextPage}
              onClick={() => void conversations.fetchNextPage()}
            >
              加载更多会话
            </button>
          )}
          {uncertain && (
            <p className="error-message" role="alert">
              会话创建结果未知。请先刷新列表并选择已创建的会话，再提交任务。
              <button
                type="button"
                onClick={() => void conversations.refetch()}
              >
                刷新会话列表
              </button>
            </p>
          )}
          <label htmlFor="question">分析问题</label>
          <textarea
            id="question"
            value={question}
            disabled={busy}
            maxLength={20000}
            required
            rows={3}
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
          <div className="form-footer">
            {taskType !== "knowledge_qa" && (
              <label className="knowledge-toggle">
                <input
                  type="checkbox"
                  checked={useKnowledge}
                  disabled={busy}
                  onChange={(event) => setUseKnowledge(event.target.checked)}
                />
                加入项目资料（RAG）
              </label>
            )}
            <p>
              后台将读取固定版本证据，生成带引用的分析建议。真实模型调用会产生
              API 用量。
            </p>
            <button
              className="primary-button"
              type="submit"
              disabled={
                busy ||
                !question.trim() ||
                conflict ||
                (uncertain && !conversationId)
              }
            >
              {busy ? "正在保存…" : error ? "重试创建任务" : "创建分析任务"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
