// 文件用途：浏览仓库、PR diff、CI 日志和项目资料原文。
"use client";

import Link from "next/link";
import { useState } from "react";
import { useWorkspace } from "@/components/workspace-context";
import { Icon } from "@/components/icon";
import {
  GitHubRepositoryForm,
  RepositoryRefresh,
} from "@/components/github-repository-form";
import { GitHubJobLogs } from "@/components/github-job-logs";
import { SourceNotices, FetchInfo } from "@/components/source-notices";
import { ciStatus } from "@/lib/ci-status";
import { QueryState as QueryMessage } from "@/components/query-state";
import { AnalysisForm } from "@/components/analysis-form";
import { useQuery } from "@tanstack/react-query";
import {
  fetchData,
  type Collection,
  type Repository,
  type PullRequestSummary,
  type PullRequestDetail,
  type CIRunSummary,
  type CIRunDetail,
  type DocumentSummary,
  type DocumentDetail,
  type RepositoryTab,
} from "@/lib/repositories";

export function RepositoryList() {
  const { repositories: query, runtime } = useWorkspace();
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("");
  const items =
    query.data?.items.filter(
      (repo) =>
        repo.full_name.toLowerCase().includes(search.toLowerCase()) &&
        (!source || repo.data_source === source),
    ) ?? [];
  return (
    <div className="management-page repository-library">
      <div className="page-heading">
        <div>
          <h1>我的仓库</h1>
          <p className="intro">浏览 PR、CI 运行和项目资料</p>
        </div>
        <button
          className="icon-button"
          aria-label="刷新仓库列表"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          <Icon name="refresh" />
        </button>
      </div>
      {(runtime.data?.data_source === "github" ||
        runtime.data?.fixture_storage === "database") && (
        <details className="repository-connect">
          <summary>＋ 添加仓库</summary>
          <GitHubRepositoryForm />
        </details>
      )}
      <div className="library-toolbar">
        <label className="search-input">
          <Icon name="search" size={18} />
          <input
            aria-label="搜索仓库"
            placeholder="搜索仓库名称…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <select
          aria-label="仓库来源"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          <option value="">全部来源</option>
          <option value="fixture">人工样例</option>
          <option value="github">GitHub</option>
        </select>
      </div>
      <QueryMessage
        pending={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
      />
      {query.data && (
        <>
          <div className="repository-table-scroll">
            <table className="repository-table">
              <thead>
                <tr>
                  <th>仓库名称</th>
                  <th>来源</th>
                  <th>PR / CI</th>
                  <th>更新时间</th>
                  <th>
                    <span className="sr-only">操作</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((repo) => (
                  <tr key={repo.id}>
                    <td>
                      <Link
                        className="repository-name"
                        href={`/repositories/${encodeURIComponent(repo.id)}`}
                      >
                        <Icon name="repo" size={24} />
                        <span>
                          <strong>{repo.full_name}</strong>
                          <small>{repo.description}</small>
                          <small>
                            {repo.language} · {repo.default_branch}
                          </small>
                        </span>
                      </Link>
                    </td>
                    <td>
                      <span className="source-badge">
                        {repo.data_source === "fixture" ? "人工样例" : "GitHub"}
                      </span>
                    </td>
                    <td>
                      {repo.pull_request_count} PR · {repo.ci_run_count} CI
                    </td>
                    <td>
                      {new Date(repo.updated_at).toLocaleDateString("zh-CN")}
                    </td>
                    <td>
                      <Link
                        className="secondary-link"
                        href={`/repositories/${encodeURIComponent(repo.id)}`}
                      >
                        打开仓库 <Icon name="arrow" size={16} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!items.length && (
            <p className="empty-panel">
              {query.data.items.length
                ? "没有匹配的仓库，请调整搜索或筛选。"
                : "暂无仓库。添加一个 GitHub 仓库后开始分析。"}
            </p>
          )}
          <p className="collection-count">
            共 {items.length} 个仓库
            {search || source ? ` · 全部 ${query.data.items.length} 个` : ""}
          </p>
        </>
      )}
    </div>
  );
}

function CodeBlock({ text, diff = false }: { text: string; diff?: boolean }) {
  // 按纯文本生成行号，由 React 转义内容，不把仓库资料当 HTML 执行。
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  return (
    <div className="code-block">
      <ol>
        {lines.map((line, i) => (
          <li
            key={i}
            className={
              diff && line.startsWith("+") && !line.startsWith("+++")
                ? "diff-add"
                : diff && line.startsWith("-") && !line.startsWith("---")
                  ? "diff-remove"
                  : line.startsWith("E   ") ||
                      line.startsWith("ERROR:") ||
                      line.startsWith("RuntimeError:")
                    ? "log-error"
                    : ""
            }
          >
            <code>{line || " "}</code>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PullRequestView({ pr }: { pr: PullRequestDetail }) {
  return (
    <section className="detail-panel" aria-labelledby="detail-title">
      <div className="detail-heading">
        <span className="resource-kicker">PULL REQUEST #{pr.number}</span>
        <h2 id="detail-title">{pr.title}</h2>
        <p>{pr.body}</p>
      </div>
      <div className="version-strip">
        <span>
          BASE <code>{pr.base_sha}</code>
        </span>
        <span>
          HEAD <code>{pr.head_sha}</code>
        </span>
      </div>
      <FetchInfo at={pr.fetched_at} />
      <SourceNotices notices={pr.warnings} />
      {pr.files_limited && (
        <p className="source-warnings">
          变更文件达到读取上限，当前列表不完整。
        </p>
      )}
      {pr.files.map((file) => (
        <div className="changed-file" key={file.path}>
          <div className="file-heading">
            <code>{file.path}</code>
            <span>
              <b className="addition">+{file.additions}</b>{" "}
              <b className="deletion">−{file.deletions}</b>
            </span>
          </div>
          {file.patch_available ? (
            <CodeBlock text={file.patch} diff />
          ) : (
            <p className="detail-note">
              GitHub 未提供此文件的 diff，当前变更内容不完整。
            </p>
          )}
          {file.head_content != null && (
            <details>
              <summary>查看 HEAD 完整文件（带行号）</summary>
              <CodeBlock text={file.head_content} />
            </details>
          )}
          {file.base_content != null && (
            <details>
              <summary>查看 BASE 完整文件（带行号）</summary>
              <CodeBlock text={file.base_content} />
            </details>
          )}
          {file.content_sha256 && (
            <p className="hash-note">
              HEAD 内容 SHA256 <code>{file.content_sha256}</code>
            </p>
          )}
          {file.previous_path && (
            <p className="hash-note">原路径 {file.previous_path}</p>
          )}
        </div>
      ))}
      {(pr.linked_issues ?? []).length > 0 && (
        <section className="linked-issues">
          <h3>正文引用的 Issue</h3>
          <p className="column-intro">
            仅包含同仓库正文引用，不代表平台上的全部关联关系。
          </p>
          {(pr.linked_issues ?? []).map((issue) => (
            <details key={issue.number}>
              <summary>
                #{issue.number} {issue.title} · {issue.state}
              </summary>
              <p>{issue.body}</p>
              <a
                className="text-link"
                href={issue.html_url}
                target="_blank"
                rel="noreferrer"
              >
                在 GitHub 查看 →
              </a>
            </details>
          ))}
        </section>
      )}
      <p className="detail-note">
        {pr.data_source === "fixture"
          ? "这是固定提交的样例变更，尚未生成 Agent 分析报告。"
          : "当前为 GitHub 实时读取的 diff 预览，文件全文及证据固定仍待接入。"}
      </p>
    </section>
  );
}

function CIRunView({ run }: { run: CIRunDetail }) {
  const state = ciStatus(run);
  return (
    <section className="detail-panel" aria-labelledby="detail-title">
      <div className="detail-heading">
        <span className="resource-kicker">CI RUN #{run.id}</span>
        <h2 id="detail-title">{run.name}</h2>
        <p>
          {stageName(run.stage)}
          {run.pull_request_number
            ? ` · 关联 PR #${run.pull_request_number}`
            : " · 未提供关联 PR"}
          {run.duration_seconds != null && ` · 耗时 ${run.duration_seconds} 秒`}{" "}
          · 第 {run.run_attempt} 次尝试
        </p>
        <span className={`ci-state ${state.tone}`}>{state.label}</span>
      </div>
      <div className="version-strip">
        <span>
          HEAD <code>{run.head_sha}</code>
        </span>
      </div>
      <FetchInfo at={run.fetched_at} />
      <SourceNotices notices={run.warnings} />
      {run.log != null ? (
        <>
          <div className="file-heading">
            <span>完整日志 · {run.log.trimEnd().split("\n").length} 行</span>
          </div>
          <CodeBlock text={run.log} />
          <p className="hash-note">
            日志 SHA256 <code>{run.log_sha256}</code>
          </p>
        </>
      ) : (
        <GitHubJobLogs key={`${run.id}:${run.run_attempt}`} run={run} />
      )}
      <p className="detail-note">
        {run.data_source === "fixture"
          ? "日志为人工构造；失败状态描述该次样例运行，不代表当前真实仓库状态。"
          : "CI状态和日志来自 GitHub，仅执行只读请求。当前预览尚未保存为分析证据。"}
      </p>
    </section>
  );
}

function DocumentView({ doc }: { doc: DocumentDetail }) {
  return (
    <section className="detail-panel" aria-labelledby="detail-title">
      <div className="detail-heading">
        <span className="resource-kicker">PROJECT DOCUMENT</span>
        <h2 id="detail-title">{doc.title}</h2>
        <p>{doc.line_count} 行 · 原文预览 · 后续可用于知识检索</p>
      </div>
      <CodeBlock text={doc.content} />
      <p className="hash-note">
        文档版本 SHA256 <code>{doc.version}</code>
      </p>
      <p className="detail-note">
        资料原文按文本展示，不执行其中的 HTML 或指令。
      </p>
    </section>
  );
}

function stageName(stage: CIRunSummary["stage"]) {
  if (stage == null) return "GitHub Actions 工作流";
  return { install: "依赖安装", test: "单元测试", configure: "启动配置" }[
    stage
  ];
}

export function RepositoryWorkspace({
  repoId,
  tab,
  selected,
}: {
  repoId: string;
  tab: RepositoryTab;
  selected?: string;
}) {
  const [search, setSearch] = useState("");
  const base = `repositories/${encodeURIComponent(repoId)}`;
  const repo = useQuery({
    queryKey: ["repository", repoId],
    queryFn: () => fetchData<Repository>(base),
  });
  const prs = useQuery({
    queryKey: ["pull-requests", repoId],
    queryFn: () =>
      fetchData<Collection<PullRequestSummary>>(`${base}/pull-requests`),
    enabled: repo.isSuccess && tab === "prs",
  });
  const runs = useQuery({
    queryKey: ["ci-runs", repoId],
    queryFn: () => fetchData<Collection<CIRunSummary>>(`${base}/ci-runs`),
    enabled: repo.isSuccess && tab === "ci",
  });
  const docs = useQuery({
    queryKey: ["documents", repoId],
    queryFn: () => fetchData<Collection<DocumentSummary>>(`${base}/documents`),
    enabled: repo.isSuccess && tab === "docs",
  });
  const activeList = tab === "prs" ? prs : tab === "ci" ? runs : docs;
  const firstId =
    tab === "prs"
      ? prs.data?.items[0]?.number
      : tab === "ci"
        ? runs.data?.items[0]?.id
        : docs.data?.items[0]?.id;
  const activeId = selected ?? (firstId == null ? undefined : String(firstId));
  const resourcePath = {
    prs: "pull-requests",
    ci: "ci-runs",
    docs: "documents",
  }[tab];
  const detail = useQuery({
    queryKey: ["resource-detail", repoId, tab, activeId],
    queryFn: () =>
      fetchData<PullRequestDetail | CIRunDetail | DocumentDetail>(
        `${base}/${resourcePath}/${encodeURIComponent(activeId!)}`,
      ),
    enabled: repo.isSuccess && Boolean(activeId),
  });
  const itemLink = (id: string | number) =>
    `/repositories/${encodeURIComponent(repoId)}?tab=${tab}&item=${encodeURIComponent(String(id))}`;
  const matches = (text: string) =>
    text.toLowerCase().includes(search.toLowerCase());
  if (repo.isPending || repo.error)
    return (
      <div className="management-page">
        <Link className="back-link" href="/repositories">
          ← 返回仓库列表
        </Link>
        <QueryMessage
          pending={repo.isPending}
          error={repo.error}
          retry={() => void repo.refetch()}
        />
      </div>
    );
  return (
    <div className="management-page repository-workspace">
      <Link className="back-link" href="/repositories">
        ← 所有仓库
      </Link>
      <div className="page-heading">
        <div>
          <h1>
            {repo.data.full_name}
            <span className="source-badge">
              {repo.data.data_source === "fixture" ? "人工样例" : "GitHub"}
            </span>
          </h1>
          <p className="intro">
            {repo.data.description} · {repo.data.language} ·{" "}
            {repo.data.default_branch}
          </p>
        </div>
        <div className="heading-actions">
          <Link
            className="secondary-link"
            href={`/runs?repo=${encodeURIComponent(repoId)}`}
          >
            打开分析工作台 <Icon name="external" size={16} />
          </Link>
          <RepositoryRefresh repo={repo.data} />
        </div>
      </div>
      <SourceNotices notices={repo.data.sync_warnings} />
      <div className="resource-tabs" role="navigation" aria-label="仓库资源">
        <Link
          className={tab === "prs" ? "tab-active" : ""}
          href={`/repositories/${repoId}?tab=prs`}
          scroll={false}
        >
          Pull requests <span>{repo.data.pull_request_count}</span>
        </Link>
        <Link
          className={tab === "ci" ? "tab-active" : ""}
          href={`/repositories/${repoId}?tab=ci`}
          scroll={false}
        >
          CI 运行 <span>{repo.data.ci_run_count}</span>
        </Link>
        <Link
          className={tab === "docs" ? "tab-active" : ""}
          href={`/repositories/${repoId}?tab=docs`}
          scroll={false}
        >
          项目资料 <span>{repo.data.document_count}</span>
        </Link>
      </div>
      <SourceNotices notices={activeList.data?.warnings} />
      <FetchInfo
        at={activeList.data?.fetched_at}
        limited={activeList.data?.limited}
      />
      <div className="resource-master-detail">
        <aside className="resource-catalog" aria-label="仓库资源列表">
          <label className="search-input">
            <Icon name="search" size={18} />
            <input
              aria-label="搜索仓库资源"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={
                tab === "prs"
                  ? "搜索 PR…"
                  : tab === "ci"
                    ? "搜索 CI…"
                    : "搜索资料…"
              }
            />
          </label>
          <QueryMessage
            pending={activeList.isPending}
            error={activeList.error}
            retry={() => void activeList.refetch()}
          />
          <div className="resource-list">
            {tab === "prs" &&
              prs.data?.items
                .filter((pr) => matches(`#${pr.number} ${pr.title}`))
                .map((pr) => (
                  <Link
                    className={`resource-row ${activeId === String(pr.number) ? "row-active" : ""}`}
                    aria-current={
                      activeId === String(pr.number) ? "true" : undefined
                    }
                    href={itemLink(pr.number)}
                    key={pr.number}
                    scroll={false}
                  >
                    <div>
                      <h3>
                        #{pr.number} {pr.title}
                      </h3>
                      <p>
                        {pr.author} · {pr.head_sha.slice(0, 8)}
                      </p>
                      <span className="source-badge">
                        {
                          { open: "Open", closed: "Closed", merged: "Merged" }[
                            pr.state
                          ]
                        }
                      </span>
                    </div>
                  </Link>
                ))}
            {tab === "ci" &&
              runs.data?.items
                .filter((run) => matches(`#${run.id} ${run.name}`))
                .map((run) => (
                  <Link
                    className={`resource-row ${activeId === String(run.id) ? "row-active" : ""}`}
                    aria-current={
                      activeId === String(run.id) ? "true" : undefined
                    }
                    href={itemLink(run.id)}
                    key={run.id}
                    scroll={false}
                  >
                    <div>
                      <h3>
                        #{run.id} {run.name}
                      </h3>
                      <p>
                        {stageName(run.stage)}
                        {run.pull_request_number
                          ? ` · PR #${run.pull_request_number}`
                          : ""}
                      </p>
                      <span className={`ci-state ${ciStatus(run).tone}`}>
                        {ciStatus(run).label}
                      </span>
                    </div>
                  </Link>
                ))}
            {tab === "docs" &&
              docs.data?.items
                .filter((doc) => matches(doc.title))
                .map((doc) => (
                  <Link
                    className={`resource-row ${activeId === doc.id ? "row-active" : ""}`}
                    aria-current={activeId === doc.id ? "true" : undefined}
                    href={itemLink(doc.id)}
                    key={doc.id}
                    scroll={false}
                  >
                    <div>
                      <h3>
                        <Icon name="file" size={18} />
                        {doc.title}
                      </h3>
                      <p>
                        {doc.kind} · {doc.line_count} 行
                      </p>
                    </div>
                  </Link>
                ))}
          </div>
          {activeList.data?.items.length === 0 && (
            <p className="empty-panel">当前分类暂无资源。</p>
          )}
          {search && activeList.data?.items.length !== 0 && (
            <p className="column-intro">仅筛选当前已载入的资源。</p>
          )}
          {tab === "docs" && (
            <Link
              className="text-link"
              href={`/knowledge?repo=${encodeURIComponent(repoId)}`}
            >
              管理项目知识库 ↗
            </Link>
          )}
        </aside>
        <div id="resource-detail" className="resource-reader">
          {activeId ? (
            <>
              <QueryMessage
                pending={detail.isPending}
                error={detail.error}
                retry={() => void detail.refetch()}
              />
              {detail.data && tab === "prs" && (
                <PullRequestView pr={detail.data as PullRequestDetail} />
              )}
              {detail.data && tab === "ci" && (
                <CIRunView run={detail.data as CIRunDetail} />
              )}
              {detail.data && tab === "docs" && (
                <DocumentView doc={detail.data as DocumentDetail} />
              )}
              {detail.data && tab !== "docs" && (
                <AnalysisForm
                  key={`${repoId}:${tab}:${activeId}`}
                  repoId={repoId}
                  taskType={tab === "prs" ? "pr_review" : "ci_debug"}
                  targetId={activeId}
                />
              )}
            </>
          ) : (
            <div className="selection-hint">
              <Icon name="file" size={32} />
              <h3>选择资源，查看原始内容</h3>
              <p>PR 展示代码变更，CI 展示运行日志，项目资料展示原文。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
