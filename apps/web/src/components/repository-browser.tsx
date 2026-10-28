// 文件用途：浏览仓库、PR diff、CI 日志和项目资料原文。
"use client";

import Link from "next/link";
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

function QueryMessage({
  pending,
  error,
  retry,
}: {
  pending: boolean;
  error: Error | null;
  retry: () => void;
}) {
  if (pending)
    return (
      <div className="resource-message" role="status">
        正在读取数据…
      </div>
    );
  if (error)
    return (
      <div className="resource-message error-message" role="alert">
        <p>{error.message}</p>
        <button onClick={retry}>重新加载</button>
      </div>
    );
  return null;
}

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
          <p className="intro">浏览固定版本的 PR 变更、CI 日志和项目资料。</p>
        </div>
        <span className="step-badge">第 03 / 24 步</span>
      </div>
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
                <strong>{repo.pull_request_count}</strong> Pull requests
              </span>
              <span>
                <strong>{repo.ci_run_count}</strong> CI 运行
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
        当前步骤提供可控的只读数据浏览；创建分析任务将在后续步骤接入。
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
      {pr.files.map((file) => (
        <div className="changed-file" key={file.path}>
          <div className="file-heading">
            <code>{file.path}</code>
            <span>
              <b className="addition">+{file.additions}</b>{" "}
              <b className="deletion">−{file.deletions}</b>
            </span>
          </div>
          <CodeBlock text={file.patch} diff />
          <details>
            <summary>查看 HEAD 完整文件（带行号）</summary>
            <CodeBlock text={file.head_content} />
          </details>
          <details>
            <summary>查看 BASE 完整文件（带行号）</summary>
            <CodeBlock text={file.base_content} />
          </details>
          <p className="hash-note">
            HEAD 内容 SHA256 <code>{file.content_sha256}</code>
          </p>
        </div>
      ))}
      <p className="detail-note">
        这是固定提交的样例变更，尚未生成 Agent 分析报告。
      </p>
    </section>
  );
}

function CIRunView({ run }: { run: CIRunDetail }) {
  return (
    <section className="detail-panel" aria-labelledby="detail-title">
      <div className="detail-heading">
        <span className="resource-kicker">CI RUN #{run.id}</span>
        <h2 id="detail-title">{run.name}</h2>
        <p>
          失败阶段：{stageName(run.stage)} · 关联 PR #{run.pull_request_number}{" "}
          · 耗时 {run.duration_seconds} 秒
        </p>
      </div>
      <div className="version-strip">
        <span>
          HEAD <code>{run.head_sha}</code>
        </span>
      </div>
      <div className="file-heading">
        <span>完整日志 · {run.log.trimEnd().split("\n").length} 行</span>
        <span className="failure-badge">运行失败</span>
      </div>
      <CodeBlock text={run.log} />
      <p className="hash-note">
        日志 SHA256 <code>{run.log_sha256}</code>
      </p>
      <p className="detail-note">
        日志为人工构造；失败状态描述该次样例运行，不代表当前真实仓库状态。
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
    enabled: tab === "prs",
  });
  const runs = useQuery({
    queryKey: ["ci-runs", repoId],
    queryFn: () => fetchData<Collection<CIRunSummary>>(`${base}/ci-runs`),
    enabled: tab === "ci",
  });
  const docs = useQuery({
    queryKey: ["documents", repoId],
    queryFn: () => fetchData<Collection<DocumentSummary>>(`${base}/documents`),
    enabled: tab === "docs",
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
    enabled: Boolean(selected),
  });
  const activeList = tab === "prs" ? prs : tab === "ci" ? runs : docs;
  const itemLink = (id: string | number) =>
    `/repositories/${encodeURIComponent(repoId)}?tab=${tab}&item=${encodeURIComponent(String(id))}`;

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
              <span className="row-state">Open ↗</span>
            </Link>
          ))}
        {tab === "ci" &&
          runs.data?.items.map((run) => (
            <Link
              className={`resource-row ${selected === String(run.id) ? "row-active" : ""}`}
              key={run.id}
              href={itemLink(run.id)}
            >
              <span className="row-icon ci-icon">×</span>
              <div>
                <h3>{run.name}</h3>
                <p>
                  #{run.id} · {stageName(run.stage)} · PR #
                  {run.pull_request_number}
                </p>
              </div>
              <span className="failure-badge">失败</span>
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
