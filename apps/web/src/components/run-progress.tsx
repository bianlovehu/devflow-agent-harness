// 文件用途：合并持久化历史与可续传 SSE，展示时间线、连接状态和独立取消/重试入口。
"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { postData } from "@/lib/api-client";
import { contiguousCursor, mergeEvents } from "@/lib/event-sequence";
import type { Run, RunEvent } from "@/lib/workflows";
import { readEvents } from "@/lib/workflows";
import { QueryState } from "@/components/query-state";

const labels: Record<string, string> = {
  "run.queued": "任务已入队",
  "run.started": "后台开始执行",
  "run.recovery_queued": "租约过期，已安排自动恢复",
  "run.resumed": "从持久化状态恢复",
  "stage.started": "阶段开始",
  "stage.completed": "阶段完成",
  "tool.started": "开始只读工具",
  "tool.completed": "只读工具完成",
  "run.cancel_requested": "已请求取消",
  "run.cancelled": "任务已取消",
  "run.succeeded": "任务完成",
  "model.started": "模型开始分析",
  "model.completed": "模型返回结果",
  "model.failed": "模型调用失败",
  "report.repair_requested": "修正报告格式或引用",
  "analysis.trace_saved": "分析调用记录已保存",
  "knowledge.retrieved": "项目资料检索完成",
  "run.failed": "任务失败",
  "run.needs_attention": "任务需要处理",
  "run.loop_detected": "连续重复工具请求，已停止",
  "budget.warning": "项目预算达到提醒线",
  "budget.blocked": "预算或报价检查阻止请求",
};
export function activeRun(run: Run) {
  return run.status === "queued" || run.status === "running";
}

export function RunControls({ run }: { run: Run }) {
  const router = useRouter();
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const retryKey = useRef<string | null>(null);
  const lock = useRef(false);
  async function act(action: "cancel" | "retry") {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      if (action === "retry") retryKey.current ??= crypto.randomUUID();
      const result = await postData<Run>(
        `runs/${run.id}/${action}`,
        {},
        action === "retry" ? retryKey.current! : undefined,
      );
      void cache.invalidateQueries({ queryKey: ["runs", run.repo_id] });
      void cache.invalidateQueries({ queryKey: ["run", run.id] });
      void cache.invalidateQueries({ queryKey: ["run-events", run.id] });
      if (action === "retry") router.push(`/runs/${result.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("操作失败，请重试"));
    } finally {
      setBusy(false);
      lock.current = false;
    }
  }
  return (
    <div className="run-controls">
      {activeRun(run) ? (
        <button
          type="button"
          disabled={busy || Boolean(run.cancel_requested_at)}
          onClick={() => void act("cancel")}
        >
          {run.cancel_requested_at
            ? "正在取消…"
            : busy
              ? "正在提交…"
              : "停止任务"}
        </button>
      ) : (
        <button type="button" disabled={busy} onClick={() => void act("retry")}>
          {busy ? "正在创建…" : "按原证据重试"}
        </button>
      )}
      <QueryState
        pending={false}
        error={error}
        retry={() => void act(activeRun(run) ? "cancel" : "retry")}
      />
    </div>
  );
}

export function RunProgress({ run }: { run: Run }) {
  const cache = useQueryClient();
  const [connection, setConnection] = useState("正在连接进度…");
  const history = useQuery({
    queryKey: ["run-events", run.id],
    queryFn: ({ signal }) => readEvents(run.id, signal),
    // 作为 SSE 不可用时的补查，合并函数保证不会把新事件覆盖为旧快照。
    structuralSharing: (oldData, newData) =>
      mergeEvents(
        run.id,
        (oldData as RunEvent[] | undefined) ?? [],
        newData as RunEvent[],
      ),
    refetchInterval: activeRun(run) ? 5000 : false,
  });
  const ready = history.isSuccess;
  useEffect(() => {
    if (!ready) return;
    const old = cache.getQueryData<RunEvent[]>(["run-events", run.id]) ?? [];
    const after = contiguousCursor(old);
    const source = new EventSource(
      `/api/backend/runs/${run.id}/stream?after=${after}`,
    );
    source.onopen = () => setConnection("进度已连接");
    source.onerror = () =>
      setConnection("连接已断开，正在续传；后台任务继续执行");
    source.addEventListener("run_event", (message) => {
      try {
        const event = JSON.parse((message as MessageEvent).data) as RunEvent;
        if (
          event.run_id !== run.id ||
          typeof event.event_type !== "string" ||
          !event.payload
        )
          return;
        cache.setQueryData<RunEvent[]>(["run-events", run.id], (before = []) =>
          mergeEvents(run.id, before, [event]),
        );
        void cache.invalidateQueries({ queryKey: ["run", run.id] });
        if (
          event.event_type.startsWith("budget.") ||
          event.event_type.startsWith("model.") ||
          event.event_type.startsWith("run.")
        ) {
          void cache.invalidateQueries({ queryKey: ["budget"] });
          void cache.invalidateQueries({ queryKey: ["run-cost", run.id] });
        }
        if (
          event.event_type === "tool.completed" ||
          event.event_type.startsWith("run.")
        )
          void cache.invalidateQueries({ queryKey: ["run-evidence", run.id] });
        void cache.invalidateQueries({ queryKey: ["runs", run.repo_id] });
      } catch {
        setConnection("进度数据暂不可用，正在补查历史记录");
      }
    });
    source.addEventListener("end", () => {
      source.close();
      setConnection("历史进度已完整保存");
      void cache.invalidateQueries({ queryKey: ["run", run.id] });
    });
    return () => source.close();
  }, [cache, ready, run.id, run.repo_id]);
  return (
    <section className="event-section">
      <h3>任务时间线</h3>
      <p className="column-intro" role="status">
        {connection}
      </p>
      <QueryState
        pending={history.isPending}
        error={history.error}
        retry={() => void history.refetch()}
      />
      <ol className="event-timeline">
        {history.data?.map((item) => (
          <li key={item.sequence} data-event-sequence={item.sequence}>
            <span className="event-dot" />
            <div>
              <strong>
                {String(
                  item.payload.label ??
                    labels[item.event_type] ??
                    item.event_type,
                )}
              </strong>
              <time>
                {new Date(item.created_at).toLocaleString("zh-CN", {
                  hour12: false,
                })}
              </time>
              <details>
                <summary>查看事件记录 #{item.sequence}</summary>
                <pre>{JSON.stringify(item.payload, null, 2)}</pre>
              </details>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
