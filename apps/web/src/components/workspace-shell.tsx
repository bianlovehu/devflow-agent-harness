// 文件用途：显示共享导航、数据来源及模型配置状态。
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchData, type RuntimeInfo } from "@/lib/repositories";

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // 这里只读取配置状态，渲染页面不会触发真实模型请求。
  const { data } = useQuery({
    queryKey: ["runtime"],
    queryFn: () => fetchData<RuntimeInfo>("runtime"),
    staleTime: 30000,
  });
  const repositoryPage = pathname.startsWith("/repositories");
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
            className={!repositoryPage ? "nav-active" : ""}
            href="/"
            aria-current={!repositoryPage ? "page" : undefined}
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
          {["分析工作台", "知识库", "长期记忆", "运行记录"].map((name) => (
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
              / {repositoryPage ? "仓库" : "工程概览"}
            </span>
          </span>
          <div className="topbar-right">
            <span className="model-config">
              {!data
                ? "模型配置待检测"
                : data.model.configured
                  ? "DeepSeek 密钥已配置"
                  : "模型密钥未配置"}
            </span>
            <span className="source-badge">{sourceLabel}</span>
          </div>
        </header>
        <div className="mobile-nav">
          <Link href="/">工程概览</Link>
          <Link href="/repositories">仓库</Link>
        </div>
        {data?.data_source === "fixture" && (
          <div className="source-notice">
            <strong>样例模式</strong> · 以下仓库、PR、CI
            日志和资料均为人工构造，浏览不会调用 GitHub 或模型。
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
