// 文件用途：验证浏览器请求保留错误码与请求标识，并正确发送幂等键。
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError, fetchData, postData } from "../src/lib/api-client.ts";
const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("业务错误保留状态错误码和请求标识", async () => {
  globalThis.fetch = async () =>
    Response.json(
      {
        detail: {
          code: "repository_mismatch",
          message: "仓库不匹配",
          request_id: "request-one",
        },
      },
      { status: 409 },
    );
  await assert.rejects(
    fetchData("runs"),
    (error) =>
      error instanceof ApiError &&
      error.status === 409 &&
      error.code === "repository_mismatch" &&
      error.requestId === "request-one" &&
      error.message === "仓库不匹配",
  );
});

test("网络和非 JSON 响应提供可重试错误", async () => {
  globalThis.fetch = async () => {
    throw new Error("disconnected");
  };
  await assert.rejects(
    fetchData("runs"),
    (error) => error.code === "network_error",
  );
  globalThis.fetch = async () => new Response("not-json");
  await assert.rejects(
    fetchData("runs"),
    (error) => error.code === "invalid_response",
  );
});

test("POST 只发送一次并保持完整的中文参数", async () => {
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(url, "/api/backend/runs");
    assert.equal(options.headers["Idempotency-Key"], "same-intent");
    assert.deepEqual(JSON.parse(options.body), { question: "分析权限问题" });
    return Response.json({ id: "run" }, { status: 201 });
  };
  assert.deepEqual(
    await postData("runs", { question: "分析权限问题" }, "same-intent"),
    { id: "run" },
  );
  assert.equal(calls, 1);
});

test("限流响应保留最早重试时间", async () => {
  const before = Date.now();
  globalThis.fetch = async () =>
    Response.json(
      {
        detail: {
          code: "github_rate_limited",
          message: "限流",
          retry_after: 60,
        },
      },
      { status: 429 },
    );
  await assert.rejects(
    fetchData("repositories"),
    (error) =>
      error.code === "github_rate_limited" && error.retryAt >= before + 60000,
  );
});
