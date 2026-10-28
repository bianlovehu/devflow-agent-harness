// 文件用途：定义前端使用的健康检查响应类型。
export type ComponentHealth = {
  status: "ok" | "error" | "pending" | "unknown";
  message: string;
  version: string | null;
};

export type HealthResponse = {
  status: "ok" | "degraded" | "unavailable";
  service: string;
  version: string;
  checked_at: string;
  checks: Record<string, ComponentHealth>;
};
