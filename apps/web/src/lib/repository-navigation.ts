// 文件用途：统一仓库入口、默认标签和跨仓库切换时的导航目标。
import type { RepositoryTab } from "./repositories";

export function repositoryTab(value: unknown): RepositoryTab {
  return value === "prs" || value === "ci" || value === "docs" ? value : "code";
}

export function repositoryLocation(
  repoId: string,
  tab: RepositoryTab = "code",
) {
  return `/repositories/${encodeURIComponent(repoId)}?tab=${tab}`;
}

export function repositorySwitchLocation(
  pathname: string,
  repoId: string,
  tab?: unknown,
) {
  if (pathname === "/" || pathname === "/repositories")
    return repositoryLocation(repoId);
  if (pathname.startsWith("/repositories/"))
    return repositoryLocation(repoId, repositoryTab(tab));
  const section = pathname.startsWith("/knowledge")
    ? "/knowledge"
    : pathname.startsWith("/memories")
      ? "/memories"
      : "/runs";
  return `${section}?repo=${encodeURIComponent(repoId)}`;
}
