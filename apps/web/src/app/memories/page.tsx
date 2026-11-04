// 文件用途：打开指定仓库的长期记忆审核工作台。
import { MemoryWorkspace } from "@/components/memory-workspace";

export default async function MemoryPage({
  searchParams,
}: {
  searchParams: Promise<{ repo?: string }>;
}) {
  const query = await searchParams;
  return (
    <MemoryWorkspace
      repoId={
        typeof query.repo === "string" &&
        /^[a-zA-Z0-9_-]{1,80}$/.test(query.repo)
          ? query.repo
          : undefined
      }
    />
  );
}
