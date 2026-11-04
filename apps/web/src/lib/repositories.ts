// 文件用途：导出由 OpenAPI 生成的仓库资源类型与统一请求函数。
import type { components } from "@/lib/generated/api";
export { fetchData } from "@/lib/api-client";
type Schema = components["schemas"];
export type Source = Schema["Repository"]["data_source"];
export type SourceNotice = Schema["SourceNotice"];
export type Collection<T> = Omit<Schema["Collection_Repository_"], "items"> & {
  items: T[];
};
export type JobLog = Schema["JobLog"];
export type RuntimeInfo = Schema["RuntimeInfo"];
export type Repository = Schema["Repository"];
export type PullRequestSummary = Schema["PullRequestSummary"];
export type PullRequestDetail = Schema["PullRequestDetail"];
export type CIRunSummary = Schema["CIRunSummary"];
export type CIRunDetail = Schema["CIRunDetail"];
export type DocumentSummary = Schema["DocumentSummary"];
export type DocumentDetail = Schema["DocumentDetail"];
export type RepositoryTab = "prs" | "ci" | "docs";
