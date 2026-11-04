// 文件用途：解析仓库与会话筛选条件并打开分析工作台。
import { RunIndex } from "@/components/run-workspace";

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ repo?: string; conversation?: string }>;
}) {
  const query = await searchParams;
  const repoId =
    typeof query.repo === "string" && /^[a-zA-Z0-9_-]{1,80}$/.test(query.repo)
      ? query.repo
      : undefined;
  const conversationId =
    typeof query.conversation === "string" &&
    /^[0-9a-f-]{36}$/i.test(query.conversation)
      ? query.conversation
      : undefined;
  return <RunIndex repoId={repoId} conversationId={conversationId} />;
}
