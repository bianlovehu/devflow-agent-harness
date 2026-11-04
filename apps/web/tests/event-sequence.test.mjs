// 文件用途：验证事件历史、重复 SSE 和乱序补查的去重与续传位置。
import assert from "node:assert/strict";
import { test } from "node:test";
import { mergeEvents, contiguousCursor } from "../src/lib/event-sequence.ts";
test("历史快照和断线重复事件不会丢记录或重复显示", () => {
  const rows = mergeEvents(
    "run",
    [
      { run_id: "run", sequence: 1 },
      { run_id: "run", sequence: 3 },
    ],
    [
      { run_id: "run", sequence: 2 },
      { run_id: "run", sequence: 3 },
      { run_id: "other", sequence: 4 },
    ],
  );
  assert.deepEqual(
    rows.map((row) => row.sequence),
    [1, 2, 3],
  );
  assert.equal(contiguousCursor(rows), 3);
  assert.equal(
    mergeEvents("run", rows, [{ run_id: "run", sequence: 1 }]).length,
    3,
  );
});
test("有缺口时从最后连续事件续传，非法序号不会前移游标", () => {
  const rows = mergeEvents(
    "run",
    [],
    [1, 3, NaN, -1, 2.5].map((sequence) => ({ run_id: "run", sequence })),
  );
  assert.deepEqual(
    rows.map((row) => row.sequence),
    [1, 3],
  );
  assert.equal(contiguousCursor(rows), 1);
});
