// 文件用途：验证四种辅助意见、报告对象位置和补查原文展示。
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  reviewAction,
  reviewTarget,
  reviewStatus,
  supplementRows,
} from "../src/lib/review-presentation.ts";

test("辅助复核只展示四种意见，不自动认证正确", () => {
  assert.deepEqual(
    ["keep", "need_evidence", "downgrade", "remove"].map(reviewAction),
    ["可保留", "需补证据", "应降为推测", "应删除"],
  );
  assert.equal(reviewStatus("completed"), "复核意见已记录");
  assert.equal(reviewStatus("skipped_budget"), "预算或次数不足，未完成复核");
  assert.equal(reviewStatus("review_unavailable"), "本次复核未完成");
});

test("复核指向原报告发现而不是删除后重新排列的下标", () => {
  assert.equal(reviewTarget("finding:2"), "原报告第 3 项发现");
  assert.equal(reviewTarget("verification_steps"), "验证建议");
});

test("补查展示理由和原文行号，不要求用户阅读工具JSON", () => {
  const value = {
    results: [
      {
        request: { reason: "核对后续日志" },
        result: {
          ok: true,
          data: {
            fragments: [
              { path: "job.log", lines: [{ line: 9, text: "error" }] },
            ],
          },
        },
      },
    ],
  };
  assert.deepEqual(supplementRows(value), [
    { reason: "核对后续日志", error: "", excerpts: "job.log\n9: error" },
  ]);
  assert.equal(
    supplementRows({
      results: [{ result: { ok: false, error: { message: "证据未采集" } } }],
    })[0].error,
    "证据未采集",
  );
  assert.deepEqual(supplementRows({}), []);
});
