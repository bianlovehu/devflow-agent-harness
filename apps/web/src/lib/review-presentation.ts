// 文件用途：用直白说法展示复核意见，不把模型意见称为认证正确。
export function reviewAction(action: string) {
  return (
    (
      {
        keep: "可保留",
        need_evidence: "需补证据",
        downgrade: "应降为推测",
        remove: "应删除",
      } as Record<string, string>
    )[action] ?? "未知意见"
  );
}

export function reviewTarget(target: string) {
  if (target.startsWith("finding:"))
    return `原报告第 ${Number(target.slice(8)) + 1} 项发现`;
  return (
    (
      {
        summary: "摘要",
        answer: "回答",
        failure_stage: "失败步骤",
        verification_steps: "验证建议",
        suggestions: "建议",
        unconfirmed: "未确认事项",
        scope: "检查范围",
      } as Record<string, string>
    )[target] ?? target
  );
}

export function reviewStatus(status: string) {
  return (
    (
      {
        completed: "复核意见已记录",
        skipped_low_risk: "本次未触发自动复核",
        skipped_budget: "预算或次数不足，未完成复核",
        review_unavailable: "本次复核未完成",
      } as Record<string, string>
    )[status] ?? "复核未完成"
  );
}

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function supplementRows(value: Record<string, unknown>) {
  const rows = Array.isArray(value.results) ? value.results : [];
  return rows.map((raw) => {
    const entry = object(raw),
      request = object(entry.request),
      result = object(entry.result);
    const fragments: string[] = [];
    function collect(raw: unknown) {
      const item = object(raw);
      if (Array.isArray(item.lines)) {
        if (item.path || item.filename)
          fragments.push(String(item.path || item.filename));
        for (const rawLine of item.lines) {
          const line = object(rawLine);
          if (typeof line.text === "string")
            fragments.push(`${line.line}: ${line.text}`);
        }
      }
      for (const key of ["fragments", "items"])
        if (Array.isArray(item[key]))
          for (const child of item[key]) collect(child);
    }
    collect(result.data);
    return {
      reason: String(request.reason ?? "补充读取材料"),
      error:
        result.ok === false
          ? String(object(result.error).message ?? "补查未取得材料")
          : "",
      excerpts: fragments.join("\n"),
    };
  });
}
