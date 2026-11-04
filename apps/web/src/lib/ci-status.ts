// 文件用途：根据真实 CI 状态生成标签，避免把运行中或无结论误判为失败。
export function ciStatus(run: { status: string; conclusion?: string | null }) {
  if (run.status !== "completed")
    return {
      label:
        (
          {
            queued: "排队中",
            in_progress: "运行中",
            waiting: "等待中",
            requested: "已请求",
            pending: "等待中",
          } as Record<string, string>
        )[run.status] ?? run.status,
      tone: "pending",
    };
  const labels: Record<string, string> = {
    success: "成功",
    failure: "失败",
    cancelled: "已取消",
    timed_out: "超时",
    action_required: "需要处理",
    neutral: "中性",
    skipped: "已跳过",
    stale: "已过期",
    startup_failure: "启动失败",
  };
  const conclusion = run.conclusion;
  return {
    label: conclusion ? (labels[conclusion] ?? conclusion) : "未提供结论",
    tone:
      conclusion === "success"
        ? "success"
        : [
              "failure",
              "timed_out",
              "action_required",
              "startup_failure",
            ].includes(conclusion ?? "")
          ? "failure"
          : "neutral",
  };
}
