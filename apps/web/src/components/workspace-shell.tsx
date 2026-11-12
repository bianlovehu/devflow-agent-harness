// 文件用途：显示共享导航、数据来源及模型配置状态。
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchData, type RuntimeInfo } from "@/lib/repositories";
import { BudgetSummary } from "@/components/budget-summary";

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // 这里只读取配置状态，渲染页面不会触发真实模型请求。
  const { data } = useQuery({
    queryKey: ["runtime"],
    queryFn: () => fetchData<RuntimeInfo>("runtime"),
    staleTime: 30000,
  });
  const analysisPage = pathname.startsWith("/runs");
  const repositoryPage = pathname.startsWith("/repositories");
  const knowledgePage = pathname.startsWith("/knowledge");
  const memoryPage = pathname.startsWith("/memories");
  const sourceLabel =
    data?.data_source === "fixture"
      ? data.fixture_storage === "database"
        ? "样例数据 · 数据库"
        : "样例数据 · 文件"
      : data?.data_source === "github"
        ? "GITHUB"
        : "数据源待检测";

  return (
    <div className="workspace">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="DevFlow 首页">
          <span className="brand-mark">
            D<span>↗</span>
          </span>
          DevFlow
        </Link>
        <span className="sidebar-caption">个人工作空间</span>
        <nav aria-label="主导航">
          <Link
            className={
              !repositoryPage && !analysisPage && !knowledgePage && !memoryPage
                ? "nav-active"
                : ""
            }
            href="/"
            aria-current={
              !repositoryPage && !analysisPage && !knowledgePage && !memoryPage
                ? "page"
                : undefined
            }
          >
            ◈<span>工程概览</span>
          </Link>
          <Link
            className={repositoryPage ? "nav-active" : ""}
            href="/repositories"
            aria-current={repositoryPage ? "page" : undefined}
          >
            ◇<span>仓库</span>
            <small className="nav-count">01</small>
          </Link>
          <Link
            className={analysisPage ? "nav-active" : ""}
            href="/runs"
            aria-current={analysisPage ? "page" : undefined}
          >
            ◇<span>分析工作台</span>
          </Link>
          <Link
            className={knowledgePage ? "nav-active" : ""}
            href="/knowledge"
            aria-current={knowledgePage ? "page" : undefined}
          >
            ▤<span>知识库</span>
          </Link>
          <Link
            className={memoryPage ? "nav-active" : ""}
            href="/memories"
            aria-current={memoryPage ? "page" : undefined}
          >
            ◇<span>长期记忆</span>
          </Link>
          {["运行记录"].map((name) => (
            <span className="nav-disabled" key={name} aria-disabled="true">
              <span aria-hidden="true">◇</span>
              <span>{name}</span>
              <small>待开发</small>
            </span>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="local-dot" />
          本地开发环境<span className="version">v0.1</span>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            工作空间
            <span className="breadcrumb">
              /{" "}
              {repositoryPage
                ? "仓库"
                : analysisPage
                  ? "分析工作台"
                  : knowledgePage
                    ? "知识库"
                    : memoryPage
                      ? "长期记忆"
                      : "工程概览"}
            </span>
          </span>
          <div className="topbar-right">
            <span className="model-config">
              {!data
                ? "模型配置待检测"
                : data.model.configured
                  ? data.model.provider === "fake"
                    ? "离线假模型"
                    : `${data.model.provider === "aliyun" ? "阿里云" : "DeepSeek"} · ${data.model.name}`
                  : "模型密钥未配置"}
            </span>
            <span className="source-badge">{sourceLabel}</span>
          </div>
        </header>
        <div className="mobile-nav">
          <Link href="/">工程概览</Link>
          <Link href="/repositories">仓库</Link>
          <Link href="/runs">分析工作台</Link>
          <Link href="/knowledge">知识库</Link>
        </div>
        {data?.data_source === "fixture" && (
          <div className="source-notice">
            <strong>样例模式</strong> · 以下仓库、PR、CI
            日志为人工构造；上传资料按各自来源标注。浏览不会调用 GitHub 或模型。
          </div>
        )}
        <BudgetSummary />
        {children}
      </main>
    </div>
  );
}
