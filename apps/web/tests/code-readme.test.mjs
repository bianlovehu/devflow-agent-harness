// 文件用途：验证 README 优先级、不可读条目过滤与根目录分页查找。
import assert from "node:assert/strict";
import { test } from "node:test";
import { loadRootReadme, selectRootReadme } from "../src/lib/code-readme.ts";

const file = (path, skip_reason = null) => ({
  path,
  kind: "file",
  skip_reason,
});

test("README 按格式优先级选择并保留真实文件名大小写", () => {
  const candidates = [
    file("README"),
    file("README.txt"),
    file("README.rst"),
    file("ReadMe.MD"),
  ];
  assert.equal(selectRootReadme(candidates), "ReadMe.MD");
  assert.equal(selectRootReadme(candidates.slice(0, 3)), "README.rst");
  assert.equal(selectRootReadme(candidates.slice(0, 2)), "README.txt");
  assert.equal(selectRootReadme(candidates.slice(0, 1)), "README");
});

test("不自动选择目录、子目录 README 或不可读取文件", () => {
  assert.equal(
    selectRootReadme([
      { path: "README.md", kind: "directory" },
      file("docs/README.md"),
      file("README.txt", "file_too_large"),
      file("README.rst", "unsupported_encoding"),
      file("main.py"),
    ]),
    null,
  );
  assert.equal(
    selectRootReadme([file("README.md", "binary_file"), file("README.txt")]),
    "README.txt",
  );
});

test("找完根目录全部分页，后续分页的高优先级 README 不遗漏", async () => {
  const offsets = [];
  const result = await loadRootReadme(async (offset) => {
    offsets.push(offset);
    return offset === 0
      ? { items: [file("README.txt")], next_offset: 100 }
      : { items: [file("readme.md")], next_offset: null };
  });
  assert.equal(result, "readme.md");
  assert.deepEqual(offsets, [0, 100]);
});

test("无 README 的根目录返回空结果，读取错误保留失败状态", async () => {
  assert.equal(
    await loadRootReadme(async () => ({ items: [], next_offset: null })),
    null,
  );
  await assert.rejects(
    loadRootReadme(async () => {
      throw new Error("读取失败");
    }),
    /读取失败/,
  );
});

test("异常分页不会形成无限请求循环", async () => {
  await assert.rejects(
    loadRootReadme(async () => ({ items: [], next_offset: 0 })),
    /分页无效/,
  );
});
