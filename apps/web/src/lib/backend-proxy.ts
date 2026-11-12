// 文件用途：按接口和方法限制代理范围，校验来源并保留任务请求的幂等语义。
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const segment = /^[a-zA-Z0-9_-]{1,120}$/;
const origins = new Set([
  "http://127.0.0.1:3000",
  "http://localhost:3000",
  ...(process.env.WEB_ORIGIN
    ? [process.env.WEB_ORIGIN.replace(/\/$/, "")]
    : []),
]);
const maxBody = 128 * 1024;

function queryKeys(path: string[], method: string): string[] | null {
  if (!path.length || path.some((part) => !segment.test(part))) return null;
  const [group, id, child] = path;
  if (group === "memories") {
    if (method === "GET" && path.length === 1)
      return ["repo_id", "limit", "offset"];
    if (
      method === "POST" &&
      path.length === 3 &&
      uuid.test(id) &&
      ["edit", "approve", "revoke"].includes(child)
    )
      return ["repo_id"];
    return null;
  }
  if (group === "knowledge") {
    if (
      method === "POST" &&
      path.length === 2 &&
      ["upload", "search"].includes(id)
    )
      return [];
    if (
      method === "POST" &&
      path.length === 3 &&
      uuid.test(id) &&
      child === "delete"
    )
      return ["repo_id"];
    if (method !== "GET") return null;
    if (path.length === 1) return ["repo_id", "limit", "offset"];
    if (path.length === 2 && id === "status") return [];
    if (path.length === 2 && uuid.test(id)) return ["repo_id"];
    if (
      path.length === 4 &&
      uuid.test(id) &&
      child === "versions" &&
      uuid.test(path[3])
    )
      return ["repo_id"];
    return null;
  }
  if (method === "POST") {
    if (
      path.length === 1 &&
      ["conversations", "runs", "repositories"].includes(group)
    )
      return [];
    if (
      group === "runs" &&
      path.length === 3 &&
      uuid.test(id) &&
      ["cancel", "retry", "memories"].includes(child)
    )
      return [];
    return group === "repositories" && path.length === 3 && child === "refresh"
      ? []
      : null;
  }
  if (method !== "GET") return null;
  if (group === "budget" && path.length === 1) return [];
  if (group === "runtime" && path.length === 1) return [];
  if (group === "repositories") {
    if (
      path.length === 7 &&
      child === "ci-runs" &&
      /^[1-9][0-9]*$/.test(path[3]) &&
      path[4] === "jobs" &&
      /^[1-9][0-9]*$/.test(path[5]) &&
      path[6] === "logs"
    )
      return [];
    if (path.length <= 2) return [];
    if (
      path.length > 4 ||
      !["pull-requests", "ci-runs", "documents"].includes(child)
    )
      return null;
    return path.length === 3 ||
      child === "documents" ||
      /^[1-9][0-9]*$/.test(path[3])
      ? []
      : null;
  }
  if (["conversations", "runs"].includes(group)) {
    if (path.length === 1)
      return group === "runs"
        ? ["repo_id", "conversation_id", "limit", "offset"]
        : ["repo_id", "limit", "offset"];
    if (!uuid.test(id)) return null;
    if (path.length === 2) return [];
    if (path.length !== 3) return null;
    if (group === "conversations" && child === "messages")
      return ["limit", "offset"];
    if (group === "runs" && child === "stream") return ["after"];
    if (group === "runs" && child === "events") return ["after", "limit"];
    if (group === "runs" && ["report", "freshness", "cost"].includes(child))
      return [];
    if (group === "runs" && child === "context") return ["call"];
    if (group === "runs" && ["evidence", "artifacts"].includes(child))
      return [];
  }
  if (group === "artifacts" && path.length === 2 && uuid.test(id))
    return ["repo_id"];
  return null;
}

function failure(status: number, code: string, message: string): Response {
  const requestId = crypto.randomUUID();
  return Response.json(
    { detail: { code, message, request_id: requestId } },
    {
      status,
      headers: { "Cache-Control": "no-store", "X-Request-ID": requestId },
    },
  );
}

export async function forwardBackend(
  request: Request,
  path: string[],
  fetcher: typeof fetch = fetch,
): Promise<Response> {
  const keys = queryKeys(path, request.method);
  if (keys === null)
    return failure(404, "not_found", "资源路径或请求方法不存在");
  const incoming = new URL(request.url);
  const params = incoming.searchParams;
  for (const [key, value] of params) {
    if (!keys.includes(key) || params.getAll(key).length !== 1)
      return failure(400, "invalid_query", "查询参数不被允许或重复");
    if (
      key === "repo_id"
        ? !/^[a-zA-Z0-9_-]{1,80}$/.test(value)
        : key === "conversation_id"
          ? !uuid.test(value)
          : !/^\d{1,9}$/.test(value) ||
            (key === "limit" && (Number(value) < 1 || Number(value) > 100)) ||
            (key === "call" && Number(value) < 1)
    )
      return failure(400, "invalid_query", "查询参数格式不正确");
  }
  if (keys.includes("repo_id") && !params.has("repo_id"))
    return failure(400, "invalid_query", "需要指定所属仓库");
  const streaming =
    path[0] === "runs" && path.length === 3 && path[2] === "stream";
  const headers = new Headers({
    Accept: streaming ? "text/event-stream" : "application/json",
  });
  if (streaming) {
    const last = request.headers.get("last-event-id");
    if (last !== null && !/^\d{1,9}$/.test(last))
      return failure(400, "invalid_event_cursor", "事件序号格式不正确");
    if (last) headers.set("Last-Event-ID", last);
  }
  let body: string | undefined;
  if (request.method === "POST") {
    const origin = request.headers.get("origin");
    if (origin !== null && !origins.has(origin))
      return failure(403, "origin_denied", "请求来源不被允许");
    if (
      request.headers
        .get("content-type")
        ?.split(";")[0]
        .trim()
        .toLowerCase() !== "application/json"
    )
      return failure(415, "invalid_content_type", "请使用 JSON 提交请求");
    const key = request.headers.get("idempotency-key");
    if (key !== null && !/^[a-zA-Z0-9_.:-]{1,128}$/.test(key))
      return failure(400, "invalid_idempotency_key", "请求标识格式不正确");
    // 逐块限制实际请求体大小，不能只信任浏览器提供的 Content-Length。
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      if (reader)
        for (;;) {
          const chunk = await reader.read();
          if (chunk.done) break;
          size += chunk.value.byteLength;
          if (
            size >
            (path[0] === "knowledge" && path[1] === "upload"
              ? 7 * 1024 * 1024
              : maxBody)
          ) {
            await reader.cancel();
            return failure(413, "body_too_large", "提交内容过长");
          }
          chunks.push(chunk.value);
        }
      body = await new Blob(chunks as BlobPart[]).text();
      JSON.parse(body);
    } catch {
      return failure(400, "invalid_json", "提交内容不是有效的 JSON");
    }
    headers.set("Content-Type", "application/json");
    if (origin) headers.set("Origin", origin);
    if (key) headers.set("Idempotency-Key", key);
  }
  try {
    // URL 仅来自服务端配置；不转发 Cookie、Authorization 或上游重定向。
    const url = new URL(
      `/api/v1/${path.map(encodeURIComponent).join("/")}`,
      process.env.BACKEND_URL ?? "http://127.0.0.1:8000",
    );
    url.search = params.toString();
    const response = await fetcher(url, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: streaming
        ? request.signal
        : AbortSignal.timeout(
            path[0] === "knowledge" ||
              (path[0] === "runs" && path[2] === "memories")
              ? 180000
              : path[0] === "repositories" ||
                  (path[0] === "runs" && path[2] === "freshness")
                ? 70000
                : 8000,
          ),
    });
    if (streaming && response.ok) {
      if (
        !response.headers.get("content-type")?.startsWith("text/event-stream")
      )
        return failure(502, "invalid_stream", "后端未返回事件流");
      // 直接传递流和取消信号，不缓冲正文；浏览器关闭连接只释放传输资源。
      return new Response(response.body, {
        status: response.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
          "X-Accel-Buffering": "no",
          "X-Request-ID": response.headers.get("x-request-id") ?? "",
        },
      });
    }
    const result = await response.json();
    const outgoing = new Headers({ "Cache-Control": "no-store" });
    for (const header of [
      "X-Request-ID",
      "Idempotency-Replayed",
      "Retry-After",
    ]) {
      const value = response.headers.get(header);
      if (value) outgoing.set(header, value);
    }
    return Response.json(result, {
      status: response.status,
      headers: outgoing,
    });
  } catch {
    return failure(503, "backend_unavailable", "后端未连接或请求超时，请重试");
  }
}
