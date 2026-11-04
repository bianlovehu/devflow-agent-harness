// 文件用途：导出任务工作流类型，并完整读取会话消息与已保存事件。
import type { components } from "@/lib/generated/api";
import { fetchData } from "@/lib/api-client";
type Schema = components["schemas"];
export type Conversation = Schema["ConversationResponse"];
export type ConversationCreate = Schema["ConversationCreate"];
export type Message = Schema["MessageResponse"];
export type Run = Schema["RunResponse"];
export type RunCreate = Schema["RunCreate"];
export type RunEvent = Schema["RunEventResponse"];
export type Evidence = Schema["EvidenceResponse"];
export type ArtifactContent = Schema["ArtifactContent"];
export type Page<T> = Omit<Schema["Page_ConversationResponse_"], "items"> & {
  items: T[];
};
export type AnalysisType = "pr_review" | "ci_debug" | "knowledge_qa";
export const runStatus = {
  queued: "已排队",
  running: "执行中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  needs_attention: "待处理",
};
export const taskName = {
  pr_review: "PR 风险审查",
  ci_debug: "CI 排障",
  knowledge_qa: "知识问答",
};

export async function readMessages(
  id: string,
  signal?: AbortSignal,
): Promise<Message[]> {
  const items: Message[] = [];
  let offset: number | null = 0;
  while (offset !== null) {
    const page: Page<Message> = await fetchData(
      `conversations/${id}/messages?limit=100&offset=${offset}`,
      { signal },
    );
    items.push(...page.items);
    offset = page.next_offset ?? null;
  }
  return items;
}

export async function readEvents(
  id: string,
  signal?: AbortSignal,
): Promise<RunEvent[]> {
  const items: RunEvent[] = [];
  let after: number | null = 0;
  while (after !== null) {
    const page: { items: RunEvent[]; next_after?: number | null } =
      await fetchData(`runs/${id}/events?limit=100&after=${after}`, { signal });
    items.push(...page.items);
    after = page.next_after ?? null;
  }
  return items;
}
