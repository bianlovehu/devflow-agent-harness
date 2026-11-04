// 文件用途：统一浏览器业务请求、错误码和请求标识，保留重试所需信息。
export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  retryAt?: number;
  constructor(
    message: string,
    status: number,
    code: string,
    requestId?: string,
    retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.retryAt = retryAfter ? Date.now() + retryAfter * 1000 : undefined;
  }
}

export async function fetchData<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/backend/${path}`, {
      ...options,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "网络连接失败，请保留当前问题并重试",
      0,
      "network_error",
    );
  }
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      body?.detail?.message ?? "请求失败，请稍后重试",
      response.status,
      body?.detail?.code ?? "request_failed",
      body?.detail?.request_id ??
        response.headers.get("x-request-id") ??
        undefined,
      Number(
        body?.detail?.retry_after ?? response.headers.get("retry-after"),
      ) || undefined,
    );
  if (body === null)
    throw new ApiError("服务返回内容不完整，请重试", 502, "invalid_response");
  return body as T;
}

export function postData<T>(
  path: string,
  data: unknown,
  key?: string,
): Promise<T> {
  return fetchData<T>(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: JSON.stringify(data),
  });
}
