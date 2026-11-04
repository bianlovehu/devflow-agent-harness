// 文件用途：提供可在页面间复用的 TanStack Query 客户端。
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/lib/api-client";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  // 每次挂载只创建一个查询客户端，路由切换时保留已有缓存。
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (count, error) =>
              count < 1 &&
              !(
                error instanceof ApiError &&
                [401, 403, 404, 409, 410, 422, 429].includes(error.status)
              ),
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
