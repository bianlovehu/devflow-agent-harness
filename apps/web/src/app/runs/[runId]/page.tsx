// 文件用途：解析任务直达地址并恢复工作台详情。
import { RunDetail } from "@/components/run-workspace";

export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <RunDetail runId={runId} />;
}
