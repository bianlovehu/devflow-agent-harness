// 文件用途：验证事实、推测、建议分别展示，建议不算缺陷，旧报告不补造分类。
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  knownState,
  reportGroups,
  supportLabel,
} from "../src/lib/report-presentation.ts";

test("事实、推测、建议分组并保留用于引用和经验提取的原始下标", () => {
  const report = {
    report_version: "2",
    findings: [
      { nature: "suggestion", title: "补充测试" },
      { nature: "fact", title: "局部筛选删除" },
      { nature: "hypothesis", title: "可能影响调用方" },
      { nature: "suggestion", title: "改善说明" },
    ],
  };
  const groups = reportGroups(report);
  assert.deepEqual(
    groups.map((g) => g.items.map((v) => v.index)),
    [[1], [2], [0, 3]],
  );
  assert.match(groups[2].label, /不计为新增缺陷/);
  assert.equal(groups[2].items[0].finding, report.findings[0]);
});

test("旧版只显示分类未知，不能猜测是事实或者缺陷", () => {
  const old = { findings: [{ title: "历史报告原文", severity: "high" }] };
  const groups = reportGroups(old);
  assert.equal(groups.length, 1);
  assert.match(groups[0].label, /分类未知/);
  assert.equal(groups[0].items[0].finding, old.findings[0]);
  assert.equal("nature" in old.findings[0], false);
});

test("未知、否、是分开；未启用不表示知识库为空", () => {
  assert.equal(knownState(null), "未知");
  assert.equal(knownState(undefined), "未知");
  assert.equal(knownState(false), "否");
  assert.equal(knownState(true), "是");
});

test("没有结论复核记录时，不能因为引用有效显示为正确", () => {
  assert.equal(supportLabel(), "尚未复核");
  assert.equal(supportLabel("not_reviewed"), "尚未复核");
  assert.equal(supportLabel("supported"), "证据支持");
  assert.equal(supportLabel("partial"), "部分支持，仍需修改");
  assert.equal(supportLabel("unsupported"), "证据不支持");
});
