// 文件用途：验证仓库概览入口、显式资源链接及跨仓库导航参数隔离。
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  repositoryLocation,
  repositorySwitchLocation,
  repositoryTab,
} from "../src/lib/repository-navigation.ts";

test("缺省或无效标签进入代码，显式资源标签保持原定位", () => {
  for (const value of [undefined, null, "", "unknown", ["prs", "ci"]])
    assert.equal(repositoryTab(value), "code");
  for (const value of ["code", "prs", "ci", "docs"])
    assert.equal(repositoryTab(value), value);
});

test("仓库入口编码标识并默认进入代码页", () => {
  assert.equal(
    repositoryLocation("repo-taskboard"),
    "/repositories/repo-taskboard?tab=code",
  );
  assert.equal(
    repositoryLocation("中文 #仓库", "ci"),
    `/repositories/${encodeURIComponent("中文 #仓库")}?tab=ci`,
  );
});

test("从概览或旧列表选择仓库直接进入对应代码页", () => {
  for (const pathname of ["/", "/repositories"])
    assert.equal(
      repositorySwitchLocation(pathname, "selected"),
      "/repositories/selected?tab=code",
    );
});

test("仓库内切换保留标签，清除旧文件、快照、提交与资源参数", () => {
  for (const tab of ["code", "prs", "ci", "docs"]) {
    const old = new URL(
      `http://localhost/repositories/old?tab=${tab}&item=123&commit=old&snapshot_id=old&path=src/old.py&line=8&end=12`,
    );
    const next = new URL(
      repositorySwitchLocation(
        old.pathname,
        "next",
        old.searchParams.get("tab"),
      ),
      old,
    );
    assert.equal(next.pathname, "/repositories/next");
    assert.deepEqual([...next.searchParams], [["tab", tab]]);
  }
});

test("其他功能切换仓库保留模块，不携带旧会话或任务", () => {
  for (const [pathname, section] of [
    ["/runs", "/runs"],
    ["/runs/old-run", "/runs"],
    ["/knowledge", "/knowledge"],
    ["/memories", "/memories"],
  ])
    assert.equal(
      repositorySwitchLocation(pathname, "next"),
      `${section}?repo=next`,
    );
});
