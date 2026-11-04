// 文件用途：浏览仓库、PR diff、CI 日志和项目资料原文。
"use client";

import Link from "next/link";
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
  const query = useQuery({
    queryKey: ["repositories"],
    queryFn: () => fetchData<Collection<Repository>>("repositories"),
  });
  return (
    <div className="main-content">
      <div className="page-heading">
        <div>
          <p className="eyebrow">REPOSITORIES</p>
          <h1>从仓库开始，查看每一份证据</h1>
          <p className="intro">浏览仓库的 PR 变更、CI 运行和项目资料。</p>
        </div>
        <span className="step-badge">第 08 / 24 步</span>
      </div>
      <GitHubRepositoryForm />
      <QueryMessage
        pending={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
      />
      {query.data?.items.length === 0 && (
        <div className="empty-panel">暂无仓库。请检查当前数据源配置。</div>
      )}
      <div className="repository-grid">
        {query.data?.items.map((repo) => (
          <Link
            className="repository-card"
            key={repo.id}
            href={`/repositories/${repo.id}`}
          >
            <div className="repository-card-top">
              <span className="service-symbol">⌘</span>
              <span className="source-badge">
                {repo.data_source === "fixture" ? "人工构造样例" : "GitHub"}
              </span>
            </div>
            <h2>{repo.full_name}</h2>
            <p>{repo.description}</p>
            <div className="repo-counts">
              <span>
                <strong>{repo.pull_request_count}</strong>{" "}
                {repo.data_source === "github" ? "已同步 PR" : "Pull requests"}
              </span>
              <span>
                <strong>{repo.ci_run_count}</strong>{" "}
                {repo.data_source === "github" ? "已同步 CI" : "CI 运行"}
              </span>
              <span>
                <strong>{repo.document_count}</strong> 项目资料
              </span>
            </div>
            <div className="repo-card-footer">
              <span>
                <i className="language-dot" />
                {repo.language} · {repo.default_branch}
              </span>
              <span>打开仓库 →</span>
            </div>
          </Link>
        ))}
      </div>
      <p className="page-note">
        {query.data?.data_source === "github"
          ? "选择仓库中的 PR 或 CI 读取详情。当前 GitHub 模式仅提供只读浏览。"
          : "选择仓库中的 PR 或 CI，即可创建分析任务并核查保存的证据。"}
      </p>
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
  const resourcePath = {
    prs: "pull-requests",
    ci: "ci-runs",
    docs: "documents",
  }[tab];
  // 缓存键包含仓库、分类和资源 ID，切换资源时不会复用上一项的详情。
  const detail = useQuery({
    queryKey: ["resource-detail", repoId, tab, selected],
    queryFn: () =>
      fetchData<PullRequestDetail | CIRunDetail | DocumentDetail>(
        `${base}/${resourcePath}/${encodeURIComponent(selected!)}`,
      ),
    enabled: repo.isSuccess && Boolean(selected),
  });
  const activeList = tab === "prs" ? prs : tab === "ci" ? runs : docs;
  const itemLink = (id: string | number) =>
    `/repositories/${encodeURIComponent(repoId)}?tab=${tab}&item=${encodeURIComponent(String(id))}#resource-detail`;

  if (repo.isPending || repo.error)
    return (
      <div className="main-content">
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
    <div className="main-content">
      <Link className="back-link" href="/repositories">
        ← 返回仓库列表
      </Link>
      <div className="page-heading repo-heading">
        <div>
          <p className="eyebrow">REPOSITORY WORKSPACE</p>
          <h1>{repo.data.full_name}</h1>
          <p className="intro">{repo.data.description}</p>
        </div>
        <span className="source-badge">
          {repo.data.data_source === "fixture" ? "人工构造样例" : "GitHub"}
        </span>
      </div>
      <Link
        className="text-link"
        href={`/runs?repo=${encodeURIComponent(repoId)}`}
      >
        打开会话与任务 →
      </Link>
      <RepositoryRefresh repo={repo.data} />
      <p>
        <Link
          className="text-link"
          href={`/knowledge?repo=${encodeURIComponent(repoId)}`}
        >
          管理此仓库知识库与知识问答 →
        </Link>
      </p>
      <SourceNotices notices={repo.data.sync_warnings} />
      <FetchInfo at={repo.data.fetched_at} />
      <div className="repository-meta">
        <span>
          <i className="language-dot" />
          {repo.data.language}
        </span>
        <span>分支 {repo.data.default_branch}</span>
        <span>
          数据时间{" "}
          {new Date(repo.data.updated_at).toLocaleString("zh-CN", {
            hour12: false,
          })}
        </span>
      </div>
      <div className="resource-tabs" role="navigation" aria-label="仓库资源">
        <Link
          className={tab === "prs" ? "tab-active" : ""}
          href={`/repositories/${repoId}?tab=prs`}
        >
          Pull requests <span>{repo.data.pull_request_count}</span>
        </Link>
        <Link
          className={tab === "ci" ? "tab-active" : ""}
          href={`/repositories/${repoId}?tab=ci`}
        >
          CI 运行 <span>{repo.data.ci_run_count}</span>
        </Link>
        <Link
          className={tab === "docs" ? "tab-active" : ""}
          href={`/repositories/${repoId}?tab=docs`}
        >
          项目资料 <span>{repo.data.document_count}</span>
        </Link>
      </div>
      <QueryMessage
        pending={activeList.isPending}
        error={activeList.error}
        retry={() => void activeList.refetch()}
      />
      <FetchInfo
        at={activeList.data?.fetched_at}
        limited={activeList.data?.limited}
      />
      <SourceNotices notices={activeList.data?.warnings} />
      {activeList.data?.items.length === 0 && (
        <div className="empty-panel">当前分类暂无资源。</div>
      )}
      <div className="resource-list">
        {tab === "prs" &&
          prs.data?.items.map((pr) => (
            <Link
              className={`resource-row ${selected === String(pr.number) ? "row-active" : ""}`}
              key={pr.number}
              href={itemLink(pr.number)}
            >
              <span className="row-icon pr-icon">⑂</span>
              <div>
                <h3>{pr.title}</h3>
                <p>
                  #{pr.number} · {pr.author} ·{" "}
                  <code>{pr.head_sha.slice(0, 10)}</code>
                </p>
              </div>
              <span className="row-state">
                {{ open: "Open", closed: "Closed", merged: "Merged" }[pr.state]}{" "}
                ↗
              </span>
            </Link>
          ))}
        {tab === "ci" &&
          runs.data?.items.map((run) => (
            <Link
              className={`resource-row ${selected === String(run.id) ? "row-active" : ""}`}
              key={run.id}
              href={itemLink(run.id)}
            >
              <span className="row-icon ci-icon">
                {ciStatus(run).tone === "success"
                  ? "✓"
                  : ciStatus(run).tone === "failure"
                    ? "×"
                    : "◷"}
              </span>
              <div>
                <h3>{run.name}</h3>
                <p>
                  #{run.id} · {stageName(run.stage)}{" "}
                  {run.pull_request_number
                    ? `· PR #${run.pull_request_number}`
                    : ""}
                </p>
              </div>
              <span className={`ci-state ${ciStatus(run).tone}`}>
                {ciStatus(run).label}
              </span>
            </Link>
          ))}
        {tab === "docs" &&
          docs.data?.items.map((doc) => (
            <Link
              className={`resource-row ${selected === doc.id ? "row-active" : ""}`}
              key={doc.id}
              href={itemLink(doc.id)}
            >
              <span className="row-icon doc-icon">▤</span>
              <div>
                <h3>{doc.title}</h3>
                <p>
                  {doc.kind} · {doc.line_count} 行 ·{" "}
                  <code>{doc.version.slice(0, 10)}</code>
                </p>
              </div>
              <span className="row-state">预览 ↗</span>
            </Link>
          ))}
      </div>
      {selected ? (
        <div id="resource-detail">
          {detail.data && tab !== "docs" && (
            <AnalysisForm
              key={`${repoId}:${tab}:${selected}`}
              repoId={repoId}
              taskType={tab === "prs" ? "pr_review" : "ci_debug"}
              targetId={selected}
            />
          )}
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
        </div>
      ) : (
        <div className="selection-hint">
          <span>↖</span>
          <div>
            <h3>选择一项资源，核查它的原始内容</h3>
            <p>
              PR 展示 diff 与代码版本，CI 展示带行号日志，项目资料展示完整原文。
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
