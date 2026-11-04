// 文件用途：解析知识库仓库筛选，打开资料维护与检索工作台。
import { KnowledgeWorkspace } from "@/components/knowledge-workspace";

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<{ repo?: string }>;
}) {
  const query = await searchParams;
  const repoId =
    typeof query.repo === "string" && /^[a-zA-Z0-9_-]{1,80}$/.test(query.repo)
      ? query.repo
      : undefined;
  return <KnowledgeWorkspace repoId={repoId} />;
}
