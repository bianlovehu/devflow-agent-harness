// 文件用途：验证拖动、窗口缩小及异常存储值不会让入口移出屏幕。
import assert from "node:assert/strict";
import { test } from "node:test";
import { clampDevPosition } from "../src/lib/dev-tool-position.ts";
test("自由拖动保留任意坐标，边界及异常坐标限制在可见窗口", () => {
  assert.deepEqual(clampDevPosition(243, 167, 1000, 700, 44), {
    x: 243,
    y: 167,
  });
  assert.deepEqual(clampDevPosition(-100, 10000, 1000, 700, 44), {
    x: 8,
    y: 648,
  });
  assert.deepEqual(clampDevPosition(NaN, Infinity, 1000, 700, 44), {
    x: 8,
    y: 8,
  });
  assert.deepEqual(clampDevPosition(900, 650, 320, 480, 54), {
    x: 258,
    y: 418,
  });
});
