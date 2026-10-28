// 文件用途：解析仓库及资源 URL 参数，并展示仓库工作区。
import { RepositoryWorkspace } from "@/components/repository-browser";
import type { RepositoryTab } from "@/lib/repositories";

export default async function RepositoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<{ tab?: string; item?: string }>;
}) {
  const { repoId } = await params;
  const query = await searchParams;
  const tab: RepositoryTab =
    query.tab === "ci" || query.tab === "docs" ? query.tab : "prs";
  const selected =
    typeof query.item === "string" && /^[a-zA-Z0-9_-]+$/.test(query.item)
      ? query.item
      : undefined;
  return <RepositoryWorkspace repoId={repoId} tab={tab} selected={selected} />;
}
