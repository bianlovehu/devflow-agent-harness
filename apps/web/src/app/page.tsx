// 文件用途：显示工程健康状态、仓库入口和开发进度。
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import type { HealthResponse } from "@/lib/health";

const labels = {
  ok: "已就绪",
  error: "未连接",
  pending: "待配置",
  unknown: "等待检测",
};
const services = [
  { id: "api", title: "API 服务", subtitle: "FastAPI" },
  { id: "database", title: "数据库", subtitle: "PostgreSQL 17" },
  { id: "pgvector", title: "向量扩展", subtitle: "pgvector" },
  { id: "migrations", title: "数据库迁移", subtitle: "Alembic" },
];

async function loadHealth(): Promise<HealthResponse> {
  const response = await fetch("/api/health", { cache: "no-store" });
  if (response.status !== 200 && response.status !== 503)
    throw new Error("无法获取服务状态，请稍后重试");
  return response.json();
}

export default function Home() {
  const { data, error, isFetching, refetch } = useQuery({
    queryKey: ["health"],
    queryFn: loadHealth,
    refetchInterval: 15000,
  });
  const ready = data?.status === "ok";

  return (
    <div className="main-content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">BUILD WITH EVIDENCE</p>
          <h1>研发协作，从证据开始</h1>
          <p className="intro">
            查看服务状态，进入仓库核查 PR、CI 日志与项目资料。
          </p>
        </div>
        <span className="step-badge">第 03 / 24 步</span>
      </div>
      <section className="overview" aria-labelledby="overview-title">
        <div>
          <span className="section-label">工程状态</span>
          <h2 id="overview-title">
            {ready
              ? "基础服务已就绪"
              : data
                ? "基础服务尚未就绪"
                : "正在检查基础服务"}
          </h2>
          <p>
            {ready
              ? "前端、后端、数据库与向量扩展已连通。"
              : "请启动本地依赖。检测结果来自实际服务，每 15 秒更新。"}
          </p>
        </div>
        <button onClick={() => void refetch()} disabled={isFetching}>
          {isFetching ? "检测中…" : "↻ 重新检测"}
        </button>
      </section>
      <div className="service-grid" aria-live="polite">
        {services.map((service) => {
          const check = data?.checks[service.id];
          const status = check?.status ?? "unknown";
          return (
            <article className="service-card" key={service.id}>
              <div className="card-top">
                <span className="service-symbol" aria-hidden="true">
                  {service.id === "api"
                    ? "⌘"
                    : service.id === "database"
                      ? "▤"
                      : service.id === "pgvector"
                        ? "⋈"
                        : "↗"}
                </span>
                <span className={`status status-${status}`}>
                  <i />
                  {labels[status]}
                </span>
              </div>
              <h3>{service.title}</h3>
              <span className="service-subtitle">{service.subtitle}</span>
              <p>
                {check?.message ??
                  (data?.status === "unavailable"
                    ? "等待后端恢复连接"
                    : "正在读取服务状态")}
              </p>
              <code>{check?.version ?? "—"}</code>
            </article>
          );
        })}
      </div>
      {error && (
        <p role="alert" className="error-message">
          {error.message}
        </p>
      )}
      <p className="check-time">
        最近检测：
        {data
          ? new Date(data.checked_at).toLocaleString("zh-CN", { hour12: false })
          : "等待首次检测"}
        <span>健康检查不调用模型</span>
      </p>
      <section className="browse-callout">
        <div>
          <span className="section-label">已接入只读浏览</span>
          <h2>先查看原始材料，再开始分析</h2>
          <p>在同一仓库里浏览变更、日志与设计约束，所有材料都有固定版本。</p>
        </div>
        <Link className="primary-link" href="/repositories">
          浏览仓库 →
        </Link>
      </section>
      <section className="next-section">
        <span className="section-label">接下来的开发</span>
        <h2>把可控样例串成完整的任务闭环</h2>
        <div className="roadmap">
          <article>
            <span>04</span>
            <div>
              <h3>完成分析工作台</h3>
              <p>连接已持久化的会话、任务和证据浏览接口。</p>
            </div>
          </article>
          <article>
            <span>05</span>
            <div>
              <h3>接入 GitHub 只读数据</h3>
              <p>读取真实 PR 与 CI 数据，并保留来源和固定提交。</p>
            </div>
          </article>
        </div>
      </section>
      <footer className="page-footer">
        <span>DevFlow / 样例数据与工程基础</span>
        <a
          href="http://127.0.0.1:8000/api/docs"
          target="_blank"
          rel="noreferrer"
        >
          查看 API 文档 ↗
        </a>
      </footer>
    </div>
  );
}
