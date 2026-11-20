// 文件用途：在服务与预算面板中显示实际依赖状态，展开期间定时更新。
"use client";
import { useQuery } from "@tanstack/react-query";
import type { HealthResponse } from "@/lib/health";
import { Icon } from "@/components/icon";
import { QueryState } from "@/components/query-state";

const labels = {
  ok: "已就绪",
  error: "未连接",
  pending: "待配置",
  unknown: "等待检测",
};
const services = [
  { id: "api", title: "API 服务" },
  { id: "database", title: "数据库" },
  { id: "pgvector", title: "向量扩展" },
  { id: "migrations", title: "数据库迁移" },
];

async function loadHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch("/api/health", { cache: "no-store", signal });
  if (response.status !== 200 && response.status !== 503)
    throw new Error("无法获取服务状态，请稍后重试");
  return response.json();
}

export function HealthSummary({ enabled }: { enabled: boolean }) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => loadHealth(signal),
    enabled,
    staleTime: 10000,
    refetchInterval: enabled ? 15000 : false,
    refetchOnWindowFocus: false,
  });
  const data = health.data;
  return (
    <section className="health-summary" aria-labelledby="health-summary-title">
      <div className="health-summary-heading">
        <strong id="health-summary-title">基础服务</strong>
        <button
          type="button"
          className="text-button"
          disabled={health.isFetching}
          onClick={() => void health.refetch()}
        >
          <Icon name="refresh" size={14} />
          {health.isFetching ? "检测中…" : "重新检测"}
        </button>
      </div>
      <p aria-live="polite">
        {data
          ? data.status === "ok"
            ? "基础服务已就绪"
            : "基础服务尚未就绪"
          : health.error
            ? "服务状态获取失败"
            : "正在检查基础服务"}
      </p>
      <QueryState
        pending={enabled && health.isPending}
        error={health.error}
        retry={() => void health.refetch()}
      />
      <ul className="health-service-list">
        {services.map((service) => {
          const check = data?.checks[service.id];
          const status = check?.status ?? "unknown";
          return (
            <li key={service.id}>
              <div className="health-service-heading">
                <span>{service.title}</span>
                <span className={`status status-${status}`}>
                  <i />
                  {labels[status]}
                </span>
              </div>
              <p>{check?.message ?? "等待服务检测"}</p>
              {check?.version && <code>{check.version}</code>}
            </li>
          );
        })}
      </ul>
      <p className="health-check-time">
        最近检测：
        {data
          ? new Date(data.checked_at).toLocaleString("zh-CN", { hour12: false })
          : "等待首次检测"}
      </p>
      <p>展开期间每 15 秒更新，健康检查不调用模型。</p>
      <a
        className="text-link"
        href="http://127.0.0.1:8000/api/docs"
        target="_blank"
        rel="noreferrer"
      >
        查看 API 文档 ↗
      </a>
    </section>
  );
}
