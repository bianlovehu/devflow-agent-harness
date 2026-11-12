// 文件用途：显示只读项目预算及按运行关联的分析、记忆提取费用。
"use client";
import { useQuery } from "@tanstack/react-query";
import { fetchData } from "@/lib/api-client";
import type { components } from "@/lib/generated/api";
import { QueryState } from "@/components/query-state";

type Budget = components["schemas"]["BudgetResponse"];
type Cost = components["schemas"]["CostResponse"];
const amount = (value: string) => Number(value).toFixed(4);

export function BudgetSummary() {
  const budget = useQuery({
    queryKey: ["budget"],
    queryFn: ({ signal }) => fetchData<Budget>("budget", { signal }),
    refetchInterval: 30000,
  });
  const value = budget.data;
  return (
    <details className="budget-summary">
      <summary>
        {value
          ? `项目费用 ¥${amount(value.settled_cny)} / ¥${value.total_cny} · ${value.status === "blocked" ? "已到停止线" : value.status === "warning" ? "预算提醒" : "预算正常"}`
          : "项目预算"}
      </summary>
      <QueryState
        pending={budget.isPending}
        error={budget.error}
        retry={() => void budget.refetch()}
      />
      {value && (
        <div>
          <p>{value.basis}；从启用后累计，不自动清零。</p>
          <p>
            已结算估算 ¥{amount(value.settled_cny)} · 预留 ¥
            {amount(value.reserved_cny)} · 可继续预留 ¥
            {amount(value.available_cny)}
          </p>
          <p>
            ¥{value.warning_cny} 提醒，¥{value.stop_cny} 停止新请求；未知用量{" "}
            {value.unknown_requests} 次。
          </p>
          <p>
            单次输入预算 {value.limits.input_tokens.toLocaleString()}{" "}
            token，输出上限 {value.limits.output_tokens.toLocaleString()}{" "}
            token；任务累计 {value.limits.total_tokens.toLocaleString()} token。
          </p>
          {value.status !== "ok" && (
            <p role="status" className="source-warning">
              {value.status === "blocked"
                ? "项目预算已到停止线，真实模型请求暂停。"
                : "项目费用及预留已达到提醒线。"}
            </p>
          )}
        </div>
      )}
    </details>
  );
}

export function RunCost({ runId }: { runId: string }) {
  const cost = useQuery({
    queryKey: ["run-cost", runId],
    queryFn: ({ signal }) => fetchData<Cost>(`runs/${runId}/cost`, { signal }),
    refetchOnMount: "always",
    refetchInterval: 30000,
  });
  return (
    <details className="run-cost">
      <summary>分析与记忆提取费用</summary>
      <QueryState
        pending={cost.isPending}
        error={cost.error}
        retry={() => void cost.refetch()}
      />
      {cost.data &&
        (!cost.data.tracked ? (
          <p>此运行未纳入费用账本，无法据此认定费用为零。</p>
        ) : (
          <>
            <p>
              已结算估算 ¥{amount(cost.data.settled_cny)}，预留 ¥
              {amount(cost.data.reserved_cny)}，未知用量{" "}
              {cost.data.unknown_requests}{" "}
              次。采用保守目录价，最终以供应商账单为准。
            </p>
            {!cost.data.requests.length && (
              <p>没有真实收费请求记录；离线假模型不计费。</p>
            )}
            {cost.data.requests.map((request, index) => (
              <details key={index}>
                <summary>
                  {request.purpose === "memory" ? "记忆提取" : "分析调用"} ·{" "}
                  {String(request.status)} · ¥
                  {String(request.settled_cny ?? request.reserved_cny)}
                </summary>
                <pre>{JSON.stringify(request, null, 2)}</pre>
              </details>
            ))}
          </>
        ))}
    </details>
  );
}
