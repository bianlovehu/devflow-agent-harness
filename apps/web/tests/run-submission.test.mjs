// 文件用途：验证重复点击只发一次请求，未知结果重试复用幂等键。
import assert from "node:assert/strict";
import { test } from "node:test";
import { RunSubmission } from "../src/lib/run-submission.ts";

const payload = {
  repo_id: "repo-taskboard",
  conversation_id: "conversation",
  task_type: "pr_review",
  target_id: "101",
  question: "检查权限",
};

test("连续点击复用进行中的请求", async () => {
  const submission = new RunSubmission();
  let calls = 0;
  let complete;
  const send = async () => {
    calls++;
    return new Promise((resolve) => {
      complete = resolve;
    });
  };
  const first = submission.submit(payload, send);
  const second = submission.submit(payload, send);
  assert.equal(first, second);
  await Promise.resolve();
  assert.equal(calls, 1);
  complete({ id: "run-one" });
  assert.equal((await second).id, "run-one");
});

test("响应丢失后重试保持同一参数和幂等键", async () => {
  const submission = new RunSubmission();
  const requests = [];
  const send = async (data, key) => {
    requests.push({ data, key });
    if (requests.length === 1) throw new Error("响应丢失");
    return { id: "saved-run" };
  };
  await assert.rejects(submission.submit(payload, send));
  const retry = await submission.submit({ ...payload }, send);
  assert.equal(retry.id, "saved-run");
  assert.deepEqual(requests[0], requests[1]);
});

test("问题或会话变化会建立新的提交意图", async () => {
  const submission = new RunSubmission();
  const keys = [];
  const send = async (_, key) => {
    keys.push(key);
    return { id: "run" };
  };
  await submission.submit(payload, send);
  await submission.submit({ ...payload, question: "检查空值" }, send);
  await submission.submit(
    { ...payload, conversation_id: "another-conversation" },
    send,
  );
  assert.equal(new Set(keys).size, 3);
});
