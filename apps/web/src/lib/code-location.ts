// 文件用途：构建固定提交代码链接，保留原始路径及准确行范围。
export function codeLocation(
  repoId: string,
  commit: string,
  path = "",
  start = 1,
  end = start,
  snapshotId?: string,
) {
  const query = new URLSearchParams({
    tab: "code",
    commit,
    path,
    line: String(start),
    end: String(end),
  });
  if (snapshotId) query.set("snapshot_id", snapshotId);
  return `/repositories/${encodeURIComponent(repoId)}?${query}`;
}
export function codeLine(value: string | null) {
  return value && /^[1-9][0-9]{0,7}$/.test(value) ? Number(value) : 1;
}
