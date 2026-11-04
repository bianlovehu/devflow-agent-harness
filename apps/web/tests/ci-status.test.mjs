// 文件用途：验证真实 CI 的运行中、成功、缺失结论和失败状态不会混淆。
import assert from "node:assert/strict";
import { test } from "node:test";
import { ciStatus } from "../src/lib/ci-status.ts";
for (const [status, conclusion, label, tone] of [
  ["in_progress", null, "运行中", "pending"],
  ["queued", null, "排队中", "pending"],
  ["completed", "success", "成功", "success"],
  ["completed", "failure", "失败", "failure"],
  ["completed", "cancelled", "已取消", "neutral"],
  ["completed", null, "未提供结论", "neutral"],
  ["completed", "timed_out", "超时", "failure"],
]) {
  test(`CI ${status}/${conclusion} 显示 ${label}`, () =>
    assert.deepEqual(ciStatus({ status, conclusion }), { label, tone }));
}
