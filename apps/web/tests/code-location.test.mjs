// 文件用途：验证固定提交路径编码与准确行号链接。
import assert from "node:assert/strict";
import { test } from "node:test";
import { codeLocation, codeLine } from "../src/lib/code-location.ts";

test("历史代码链接保留提交、特殊路径和范围", () => {
  const url = new URL(
    codeLocation(
      "repo-taskboard",
      "a".repeat(40),
      "src/中文 #x.ts",
      8,
      12,
      "snapshot",
    ),
    "http://localhost",
  );
  assert.equal(url.searchParams.get("commit"), "a".repeat(40));
  assert.equal(url.searchParams.get("path"), "src/中文 #x.ts");
  assert.equal(url.searchParams.get("line"), "8");
  assert.equal(url.searchParams.get("end"), "12");
  assert.equal(url.searchParams.get("snapshot_id"), "snapshot");
});
test("行号拒绝负数、非数字和无界输入", () => {
  assert.equal(codeLine("42"), 42);
  for (const value of [null, "0", "-1", "x", "999999999999"])
    assert.equal(codeLine(value), 1);
});
