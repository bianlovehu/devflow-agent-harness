// 文件用途：查看逐次输入压缩效果、估算误差及脱敏后的压缩前材料。
"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchData } from "@/lib/api-client";
import { QueryState } from "@/components/query-state";

type Call = {
  call: number;
  context?: {
    estimated_before: number;
    estimated_input: number;
    saved_tokens: number;
    actual_prompt_tokens?: number;
    estimation_error?: number;
    stages: string[];
  };
  original_request?: unknown;
  request?: unknown;
  recovery?: boolean;
};
type Output = { calls: Call[]; recovery_count: number };
export function ContextHistory({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const context = useQuery({
    queryKey: ["context", runId],
    queryFn: () => fetchData<Output>(`runs/${runId}/context`),
    enabled: open,
  });
  const detail = useQuery({
    queryKey: ["context", runId, selected],
    queryFn: () => fetchData<Output>(`runs/${runId}/context?call=${selected}`),
    enabled: open && selected !== null,
  });
  return (
    <details
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="context-history"
    >
      <summary>上下文与恢复记录</summary>
      <QueryState
        pending={open && context.isPending}
        error={context.error}
        retry={() => void context.refetch()}
      />
      {context.data && (
        <>
          <p>
            自动恢复 {context.data.recovery_count} 次 · token
            为保守估算，实际用量来自模型供应商。
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>调用</th>
                  <th>压缩前</th>
                  <th>发送估算</th>
                  <th>节省</th>
                  <th>实际输入 / 误差</th>
                  <th>材料</th>
                </tr>
              </thead>
              <tbody>
                {context.data.calls.map((call) => (
                  <tr key={call.call}>
                    <td>
                      {call.call}
                      {call.recovery ? "（恢复）" : ""}
                    </td>
                    <td>{call.context?.estimated_before}</td>
                    <td>{call.context?.estimated_input}</td>
                    <td>{call.context?.saved_tokens}</td>
                    <td>
                      {call.context?.actual_prompt_tokens ?? "未知"} /{" "}
                      {call.context?.estimation_error ?? "未知"}
                    </td>
                    <td>
                      <button onClick={() => setSelected(call.call)}>
                        查看
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {selected !== null && (
        <>
          <QueryState
            pending={detail.isPending}
            error={detail.error}
            retry={() => void detail.refetch()}
          />
          <details open>
            <summary>第 {selected} 次压缩前材料（已脱敏）</summary>
            <pre>
              {JSON.stringify(detail.data?.calls[0]?.original_request, null, 2)}
            </pre>
          </details>
          <details>
            <summary>实际发送的压缩结果</summary>
            <pre>{JSON.stringify(detail.data?.calls[0]?.request, null, 2)}</pre>
          </details>
        </>
      )}
    </details>
  );
}
