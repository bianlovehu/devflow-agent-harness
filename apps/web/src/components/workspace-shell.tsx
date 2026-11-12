// 文件用途：显示统一导航、仓库切换和会话列表，并收纳服务配置与预算。
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { fetchData } from "@/lib/api-client";
import type { Conversation, Page } from "@/lib/workflows";
import { BudgetSummary } from "@/components/budget-summary";
import {
  WorkspaceProvider,
  useWorkspace,
} from "@/components/workspace-context";
import { DevFlowMark, Icon } from "@/components/icon";
import { QueryState } from "@/components/query-state";

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const {
    repoId,
    repositories,
    runtime,
    conversationId,
    available,
    href,
    chooseRepository,
  } = useWorkspace();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const conversations = useInfiniteQuery({
    queryKey: ["conversations", repoId],
    queryFn: ({ pageParam, signal }) =>
      fetchData<Page<Conversation>>(
        `conversations?repo_id=${encodeURIComponent(repoId!)}&limit=50&offset=${pageParam}`,
        { signal },
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: Boolean(repoId) && available,
  });
  const active = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: ({ signal }) =>
      fetchData<Conversation>(`conversations/${conversationId}`, { signal }),
    enabled: Boolean(conversationId) && available,
  });
  const items = (conversations.data?.pages.flatMap((p) => p.items) ?? []).sort(
    (a, b) =>
      b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id),
  );
  const nav = [
    { path: "/runs", label: "分析工作台", icon: "chat" },
    { path: "/repositories", label: "仓库", icon: "repo" },
    { path: "/knowledge", label: "知识库", icon: "book" },
    { path: "/memories", label: "长期记忆", icon: "memory" },
  ] as const;
  const page = nav.find((item) => pathname.startsWith(item.path));
  const title = pathname.startsWith("/runs")
    ? active.data && active.data.repo_id === repoId
      ? active.data.title
      : "新建会话"
    : (page?.label ?? "工程概览");
  return (
    <div
      className={`workspace ${collapsed ? "sidebar-collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`}
    >
      {mobileOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="关闭导航"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className="sidebar">
        <div className="brand-row">
          <Link className="brand" href="/" aria-label="DevFlow 首页">
            <DevFlowMark />
            <span>DevFlow</span>
          </Link>
          <button
            className="icon-button collapse-sidebar"
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed(!collapsed)}
          >
            <Icon name="panel" size={18} />
          </button>
          <button
            className="icon-button close-mobile"
            aria-label="关闭导航"
            onClick={() => setMobileOpen(false)}
          >
            <Icon name="close" />
          </button>
        </div>
        <label className="sidebar-repository">
          <Icon name="repo" size={18} />
          <select
            aria-label="当前仓库"
            value={repoId ?? ""}
            onChange={(e) => {
              chooseRepository(e.target.value);
              setMobileOpen(false);
            }}
            disabled={!repositories.data?.items.length}
          >
            {!repositories.data?.items.length && (
              <option value="">暂无仓库</option>
            )}
            {repoId &&
              !repositories.data?.items.some((r) => r.id === repoId) && (
                <option value={repoId}>仓库不可用</option>
              )}
            {repositories.data?.items.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.full_name}
              </option>
            ))}
          </select>
        </label>
        <Link
          className="new-conversation"
          href={href("/runs")}
          onClick={() => setMobileOpen(false)}
          title="新建会话"
        >
          <Icon name="plus" />
          <span>新建会话</span>
        </Link>
        <nav aria-label="主导航">
          {nav.map((item) => (
            <Link
              key={item.path}
              className={page?.path === item.path ? "nav-active" : ""}
              href={item.path === "/repositories" ? item.path : href(item.path)}
              aria-current={page?.path === item.path ? "page" : undefined}
              title={item.label}
              onClick={() => setMobileOpen(false)}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
        <section className="sidebar-conversations" aria-label="会话列表">
          <span className="sidebar-caption">最近会话</span>
          <div className="sidebar-conversation-scroll">
            <QueryState
              pending={Boolean(repoId) && available && conversations.isPending}
              error={conversations.error}
              retry={() => void conversations.refetch()}
            />
            {items.map((item) => (
              <Link
                className={
                  item.id === conversationId && pathname.startsWith("/runs")
                    ? "sidebar-conversation selected"
                    : "sidebar-conversation"
                }
                aria-current={
                  item.id === conversationId && pathname.startsWith("/runs")
                    ? "page"
                    : undefined
                }
                key={item.id}
                href={`/runs?repo=${encodeURIComponent(repoId!)}&conversation=${item.id}`}
                title={item.title}
                onClick={() => setMobileOpen(false)}
              >
                {item.title}
              </Link>
            ))}
            {available && conversations.isSuccess && !items.length && (
              <p className="sidebar-empty">还没有会话，开始一次新的分析。</p>
            )}
            {!available && runtime.data && (
              <p className="sidebar-empty">数据库模式下可保存会话。</p>
            )}
            {conversations.hasNextPage && (
              <button
                className="text-button"
                disabled={conversations.isFetchingNextPage}
                onClick={() => void conversations.fetchNextPage()}
              >
                加载更多会话
              </button>
            )}
          </div>
        </section>
        <div className="sidebar-footer">
          <span className="profile-avatar">D</span>
          <span className="profile-label">本地工作空间</span>
          <Link
            href="/"
            className="icon-button"
            aria-label="工程概览"
            title="工程概览"
          >
            <Icon name="home" size={18} />
          </Link>
        </div>
      </aside>
      <main className="workspace-main">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="打开导航"
            onClick={() => setMobileOpen(true)}
          >
            <Icon name="panel" />
          </button>
          {collapsed && (
            <button
              className="icon-button expand-sidebar"
              aria-label="展开侧栏"
              onClick={() => setCollapsed(false)}
            >
              <Icon name="panel" />
            </button>
          )}
          <span className="topbar-title">{title}</span>
          <div className="topbar-right">
            {runtime.data?.data_source === "fixture" && (
              <span className="source-badge">样例数据</span>
            )}
            <details className="workspace-info">
              <summary aria-label="服务状态与项目预算">
                <Icon name="settings" size={18} />
                <span>服务与预算</span>
              </summary>
              <div className="workspace-info-popover">
                <strong>运行环境</strong>
                <p>
                  {runtime.data?.data_source === "fixture"
                    ? "样例仓库、PR 与 CI 为人工构造。上传资料按各自来源标注。"
                    : "GitHub 只读接入"}
                </p>
                <p>
                  {!runtime.data
                    ? "正在检测模型配置…"
                    : runtime.data.model.configured
                      ? runtime.data.model.provider === "fake"
                        ? "离线演示模型"
                        : `${runtime.data.model.provider === "aliyun" ? "阿里云" : "DeepSeek"} · ${runtime.data.model.name}`
                      : "模型密钥未配置"}
                </p>
                <BudgetSummary />
              </div>
            </details>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  return (
    <WorkspaceProvider>
      <Shell>{children}</Shell>
    </WorkspaceProvider>
  );
}
