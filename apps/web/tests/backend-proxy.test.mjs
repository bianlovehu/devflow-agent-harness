// 文件用途：验证业务代理的白名单、来源、查询透传及幂等响应边界。
import assert from "node:assert/strict";
import { test } from "node:test";
import { forwardBackend } from "../src/lib/backend-proxy.ts";

const id = "2d4c74aa-6520-4da5-914f-b7216e87f14a";
const address = "http://127.0.0.1:3000/api/backend/";
const never = () => {
  throw new Error("不应调用后端");
};
function post(path, body = "{}", headers = {}) {
  return new Request(address + path, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

for (const path of [
  "runtime",
  "budget",
  "repositories",
  "repositories/repo-taskboard",
  "repositories/repo-taskboard/pull-requests/101",
  "repositories/repo-taskboard/ci-runs/201",
  "repositories/repo-taskboard/documents/architecture",
  `runs/${id}`,
  `runs/${id}/events?after=1&limit=20`,
  `runs/${id}/evidence`,
  `runs/${id}/artifacts`,
  `runs/${id}/report`,
  `runs/${id}/cost`,
  `runs/${id}/context`,
  `runs/${id}/context?call=1`,
  `runs/${id}/freshness`,
  "memories?repo_id=repo-taskboard&offset=0&limit=50",
  `conversations/${id}/messages?offset=50&limit=50`,
  "conversations?repo_id=repo-taskboard&offset=0&limit=50",
  "runs?repo_id=repo-taskboard",
  `runs?repo_id=repo-taskboard&conversation_id=${id}&offset=50&limit=50`,
  `artifacts/${id}?repo_id=repo-taskboard`,
  "knowledge?repo_id=repo-taskboard&offset=0&limit=20",
  "knowledge/status",
  `knowledge/${id}?repo_id=repo-taskboard`,
  `knowledge/${id}/versions/${id}?repo_id=repo-taskboard`,
]) {
  test(`转发已允许的 GET ${path}`, async () => {
    let called = 0;
    const response = await forwardBackend(
      new Request(address + path),
      path.split("?")[0].split("/"),
      async (url, options) => {
        called++;
        assert.equal(url.pathname, "/api/v1/" + path.split("?")[0]);
        assert.equal(
          url.searchParams.toString(),
          new URL(address + path).searchParams.toString(),
        );
        assert.equal(options.method, "GET");
        assert.equal(options.redirect, "error");
        return Response.json({ items: [] });
      },
    );
    assert.equal(response.status, 200);
    assert.equal(called, 1);
  });
}

test("记忆提取和审核只访问本地白名单接口，并保持来源边界", async () => {
  for (const path of [
    `runs/${id}/memories`,
    ...["edit", "approve", "revoke"].map(
      (action) => `memories/${id}/${action}?repo_id=repo-taskboard`,
    ),
  ]) {
    const response = await forwardBackend(
      post(path),
      path.split("?")[0].split("/"),
      async () => Response.json({ status: "pending" }),
    );
    assert.equal(response.status, 200);
    const denied = await forwardBackend(
      post(path, "{}", { Origin: "https://evil.example" }),
      path.split("?")[0].split("/"),
      never,
    );
    assert.equal(denied.status, 403);
  }
  assert.equal(
    (
      await forwardBackend(
        post(`memories/${id}/approve`),
        ["memories", id, "approve"],
        never,
      )
    ).status,
    400,
  );
  assert.equal(
    (
      await forwardBackend(
        new Request(address + `runs/${id}/context?call=0`),
        ["runs", id, "context"],
        never,
      )
    ).status,
    400,
  );
  assert.equal(
    (
      await forwardBackend(
        post(`runs/${id}/publish`),
        ["runs", id, "publish"],
        never,
      )
    ).status,
    404,
  );
});

test("知识库只允许上传检索与仓库内删除，并单独限制上传体积", async () => {
  for (const path of [
    "knowledge/upload",
    "knowledge/search",
    `knowledge/${id}/delete?repo_id=repo-taskboard`,
  ]) {
    const response = await forwardBackend(
      post(path),
      path.split("?")[0].split("/"),
      async () => Response.json({ ok: true }),
    );
    assert.equal(response.status, 200);
  }
  const body = JSON.stringify({ content_base64: "a".repeat(200000) });
  assert.equal(
    (
      await forwardBackend(
        post("knowledge/upload", body),
        ["knowledge", "upload"],
        async () => Response.json({ ok: true }),
      )
    ).status,
    200,
  );
  assert.equal(
    (await forwardBackend(post("runs", body), ["runs"], never)).status,
    413,
  );
  assert.equal(
    (
      await forwardBackend(
        post(
          "knowledge/upload",
          JSON.stringify({ content_base64: "a".repeat(7 * 1024 * 1024) }),
        ),
        ["knowledge", "upload"],
        never,
      )
    ).status,
    413,
  );
  assert.equal(
    (
      await forwardBackend(
        post(`knowledge/${id}/delete`),
        ["knowledge", id, "delete"],
        never,
      )
    ).status,
    400,
  );
});

test("非法路径和额外层级不会访问后端", async () => {
  for (const path of [
    ["config"],
    ["repositories", "repo", "documents", "doc", "extra"],
    ["runs", "unknown"],
    ["runs", id, "cancel"],
    ["..", "runtime"],
    ["repositories", "repo", "pull-requests", "0"],
  ]) {
    const response = await forwardBackend(new Request(address), path, never);
    assert.equal(response.status, 404);
  }
  for (const path of [
    ["runs", id],
    ["conversations", id, "messages"],
  ])
    assert.equal((await forwardBackend(post(""), path, never)).status, 404);
});

test("缺失重复未知或无效查询参数在代理层拒绝", async () => {
  for (const path of [
    "runs",
    `artifacts/${id}`,
    "runs?repo_id=repo&repo_id=other",
    "runs?repo_id=repo&url=https://other",
    "runs?repo_id=repo&limit=101",
    "runs?repo_id=repo&limit=0",
    "runs?repo_id=repo&offset=-1",
    "runs?repo_id=repo%2Fother",
    "runs?repo_id=repo&conversation_id=invalid",
    `runs?repo_id=repo&conversation_id=${id}&conversation_id=${id}`,
    `conversations?repo_id=repo&conversation_id=${id}`,
    `runs/${id}/events?after=bad`,
    "runtime?repo_id=repo",
  ]) {
    assert.equal(
      (
        await forwardBackend(
          new Request(address + path),
          path.split("?")[0].split("/"),
          never,
        )
      ).status,
      400,
    );
  }
});

test("跨来源写入在调用后端前拒绝", async () => {
  for (const origin of [
    "https://evil.example",
    "null",
    "http://localhost:3001",
  ])
    assert.equal(
      (
        await forwardBackend(
          post("runs", "{}", { Origin: origin }),
          ["runs"],
          never,
        )
      ).status,
      403,
    );
});

test("写请求限制 JSON 和实际体积", async () => {
  assert.equal(
    (
      await forwardBackend(
        post("runs", "{}", { "Content-Type": "text/plain" }),
        ["runs"],
        never,
      )
    ).status,
    415,
  );
  assert.equal(
    (await forwardBackend(post("runs", "broken"), ["runs"], never)).status,
    400,
  );
  assert.equal(
    (
      await forwardBackend(
        post("runs", JSON.stringify({ question: "文".repeat(50000) })),
        ["runs"],
        never,
      )
    ).status,
    413,
  );
  assert.equal(
    (
      await forwardBackend(
        post("runs", "{}", { "Idempotency-Key": "invalid/key" }),
        ["runs"],
        never,
      )
    ).status,
    400,
  );
});

for (const status of [200, 201, 409, 422])
  test(`原样保留后端 ${status} 与幂等请求信息`, async () => {
    const payload = { repo_id: "repo-taskboard", question: "检查权限" };
    const responseBody =
      status >= 400
        ? {
            detail: {
              code: "idempotency_conflict",
              message: "请求冲突",
              request_id: "trace-123",
            },
          }
        : { id };
    const response = await forwardBackend(
      post("runs", JSON.stringify(payload), {
        Origin: "http://127.0.0.1:3000",
        "Idempotency-Key": "intent-123",
        Cookie: "private-cookie",
        Authorization: "secret",
      }),
      ["runs"],
      async (_, options) => {
        assert.equal(options.method, "POST");
        assert.equal(options.headers.get("Idempotency-Key"), "intent-123");
        assert.equal(options.headers.get("Origin"), "http://127.0.0.1:3000");
        assert.equal(options.headers.has("Cookie"), false);
        assert.equal(options.headers.has("Authorization"), false);
        assert.deepEqual(JSON.parse(options.body), payload);
        return Response.json(responseBody, {
          status,
          headers: {
            "X-Request-ID": "trace-123",
            "Idempotency-Replayed": String(status === 200),
          },
        });
      },
    );
    assert.equal(response.status, status);
    assert.equal(response.headers.get("X-Request-ID"), "trace-123");
    assert.equal(
      response.headers.get("Idempotency-Replayed"),
      String(status === 200),
    );
    assert.deepEqual(await response.json(), responseBody);
  });

test("后端超时只尝试一次并给出可追踪错误", async () => {
  let calls = 0;
  const response = await forwardBackend(post("runs"), ["runs"], async () => {
    calls++;
    throw new Error("timeout");
  });
  const result = await response.json();
  assert.equal(calls, 1);
  assert.equal(response.status, 503);
  assert.equal(result.detail.code, "backend_unavailable");
  assert.ok(result.detail.request_id);
});

test("允许本地仓库登记刷新和受限 job 日志读取", async () => {
  for (const path of ["repositories", "repositories/github-123/refresh"]) {
    let called = false;
    const response = await forwardBackend(
      post(path),
      path.split("/"),
      async (_, options) => {
        called = true;
        assert.equal(options.method, "POST");
        return Response.json({ id: "github-123" });
      },
    );
    assert.equal(response.status, 200);
    assert.equal(called, true);
  }
  const response = await forwardBackend(
    new Request(address + "repositories/github-123/ci-runs/10/jobs/20/logs"),
    ["repositories", "github-123", "ci-runs", "10", "jobs", "20", "logs"],
    async () =>
      Response.json(
        { detail: { code: "github_rate_limited", retry_after: 60 } },
        { status: 429, headers: { "Retry-After": "60" } },
      ),
  );
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("Retry-After"), "60");
  assert.equal((await response.json()).detail.retry_after, 60);
});

test("SSE 直接透传事件流、取消信号和续传头，不缓冲为 JSON", async () => {
  const controller = new AbortController();
  const request = new Request(address + `runs/${id}/stream?after=2`, {
    signal: controller.signal,
    headers: { "Last-Event-ID": "4", Authorization: "do-not-forward" },
  });
  const result = await forwardBackend(
    request,
    ["runs", id, "stream"],
    async (url, options) => {
      assert.equal(options.headers.get("Last-Event-ID"), "4");
      assert.equal(options.headers.get("Authorization"), null);
      assert.equal(options.signal, request.signal);
      return new Response("id: 5\nevent: run_event\ndata: {}\n\n", {
        headers: { "Content-Type": "text/event-stream" },
      });
    },
  );
  assert.match(result.headers.get("content-type"), /text\/event-stream/);
  assert.match(await result.text(), /id: 5/);
});
test("取消和重试仅允许 POST，重试幂等键保持原值", async () => {
  for (const child of ["cancel", "retry"]) {
    const result = await forwardBackend(
      post(`runs/${id}/${child}`, "{}", { "Idempotency-Key": "retry-1" }),
      ["runs", id, child],
      async (url, options) => {
        assert.equal(options.headers.get("Idempotency-Key"), "retry-1");
        return Response.json({ status: "queued" });
      },
    );
    assert.equal(result.status, 200);
  }
});

test("记忆检索、重新索引与来源撤销受白名单和来源校验约束", async () => {
  for (const path of [
    "memories/search",
    `memories/${id}/index?repo_id=repo-taskboard`,
    `runs/${id}/memories/revoke-source`,
  ]) {
    const parts = path.split("?")[0].split("/");
    assert.equal(
      (
        await forwardBackend(post(path), parts, async () =>
          Response.json({ ok: true }),
        )
      ).status,
      200,
    );
    assert.equal(
      (
        await forwardBackend(
          post(path, "{}", { Origin: "https://evil.example" }),
          parts,
          never,
        )
      ).status,
      403,
    );
  }
  assert.equal(
    (
      await forwardBackend(
        post("memories/search/extra"),
        ["memories", "search", "extra"],
        never,
      )
    ).status,
    404,
  );
});
