// 文件用途：定义资源接口类型，并封装统一的只读数据请求。
export type Source = "fixture" | "github";
export type Collection<T> = { data_source: Source; items: T[] };
export type RuntimeInfo = {
  data_source: Source;
  fixture_storage: "database" | "files";
  task_execution_available: boolean;
  repository_adapter_available: boolean;
  model: { provider: string; name: string; configured: boolean };
};
export type Repository = {
  id: string;
  data_source: Source;
  full_name: string;
  description: string;
  language: string;
  default_branch: string;
  default_commit: string;
  updated_at: string;
  pull_request_count: number;
  ci_run_count: number;
  document_count: number;
};
export type PullRequestSummary = {
  repo_id: string;
  data_source: Source;
  number: number;
  title: string;
  body: string;
  author: string;
  state: "open" | "closed" | "merged";
  base_sha: string;
  head_sha: string;
  updated_at: string;
};
export type ChangedFile = {
  path: string;
  additions: number;
  deletions: number;
  patch: string;
  base_content: string;
  head_content: string;
  content_sha256: string;
};
export type PullRequestDetail = PullRequestSummary & { files: ChangedFile[] };
export type CIRunSummary = {
  id: number;
  repo_id: string;
  data_source: Source;
  pull_request_number: number;
  name: string;
  conclusion: "success" | "failure" | "cancelled";
  stage: "install" | "test" | "configure";
  head_sha: string;
  started_at: string;
  duration_seconds: number;
};
export type CIRunDetail = CIRunSummary & { log: string; log_sha256: string };
export type DocumentSummary = {
  id: string;
  repo_id: string;
  data_source: Source;
  title: string;
  kind: string;
  version: string;
  updated_at: string;
  line_count: number;
};
export type DocumentDetail = DocumentSummary & { content: string };
export type RepositoryTab = "prs" | "ci" | "docs";

export async function fetchData<T>(path: string): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail?.message ?? "数据读取失败，请稍后重试");
  }
  return body as T;
}
