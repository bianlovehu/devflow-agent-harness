// 文件用途：所有仓库页签共用页头与固定顺序导航，切换时只更换下方内容。
"use client";
import Link from "next/link";
import type { Repository, RepositoryTab } from "@/lib/repositories";
import { Icon } from "@/components/icon";
import { RepositoryRefresh } from "@/components/github-repository-form";
import { SourceNotices } from "@/components/source-notices";

export function RepositoryHeader({
  repo,
  tab,
}: {
  repo: Repository;
  tab: RepositoryTab;
}) {
  const repoId = repo.id;
  return (
    <>
      <Link className="back-link" href="/repositories">
        ← 所有仓库
      </Link>
      <div className="page-heading">
        <div>
          <h1>
            {repo.full_name}
            <span className="source-badge">
              {repo.data_source === "fixture" ? "人工样例" : "GitHub"}
            </span>
          </h1>
          <p className="intro">
            {repo.description} · {repo.language} · {repo.default_branch}
          </p>
        </div>
        <div className="heading-actions">
          <Link
            className="secondary-link"
            href={`/runs?repo=${encodeURIComponent(repoId)}`}
          >
            打开分析工作台 <Icon name="external" size={16} />
          </Link>
          <RepositoryRefresh repo={repo} />
        </div>
      </div>
      <SourceNotices notices={repo.sync_warnings} />
      <div className="resource-tabs" role="navigation" aria-label="仓库资源">
        <Link
          className={tab === "code" ? "tab-active" : ""}
          aria-current={tab === "code" ? "page" : undefined}
          href={`/repositories/${repoId}?tab=code`}
          scroll={false}
        >
          代码
        </Link>
        <Link
          className={tab === "prs" ? "tab-active" : ""}
          aria-current={tab === "prs" ? "page" : undefined}
          href={`/repositories/${repoId}?tab=prs`}
          scroll={false}
        >
          Pull requests <span>{repo.pull_request_count}</span>
        </Link>
        <Link
          className={tab === "ci" ? "tab-active" : ""}
          aria-current={tab === "ci" ? "page" : undefined}
          href={`/repositories/${repoId}?tab=ci`}
          scroll={false}
        >
          CI 运行 <span>{repo.ci_run_count}</span>
        </Link>
        <Link
          className={tab === "docs" ? "tab-active" : ""}
          aria-current={tab === "docs" ? "page" : undefined}
          href={`/repositories/${repoId}?tab=docs`}
          scroll={false}
        >
          项目资料 <span>{repo.document_count}</span>
        </Link>
      </div>
    </>
  );
}
