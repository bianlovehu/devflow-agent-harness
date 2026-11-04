// 文件用途：统一加载与错误提示，并遵守限流响应中的最早重试时间。
"use client";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api-client";

export function QueryState({
  pending,
  error,
  retry,
}: {
  pending: boolean;
  error: Error | null;
  retry: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const retryAt = error instanceof ApiError ? error.retryAt : undefined;
  useEffect(() => {
    if (!retryAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [retryAt]);
  const wait = retryAt ? Math.max(0, Math.ceil((retryAt - now) / 1000)) : 0;
  if (error)
    return (
      <div className="resource-message error-message" role="alert">
        <p>{error.message}</p>
        {error instanceof ApiError && (
          <p className="request-detail">
            {error.code}
            {error.requestId && ` · 请求 ${error.requestId}`}
          </p>
        )}
        <button type="button" onClick={retry} disabled={wait > 0}>
          {wait ? `${wait} 秒后可重试` : "重新加载"}
        </button>
      </div>
    );
  if (pending)
    return (
      <div className="resource-message" role="status">
        正在读取数据…
      </div>
    );
  return null;
}
