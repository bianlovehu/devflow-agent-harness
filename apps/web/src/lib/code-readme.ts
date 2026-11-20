// 文件用途：从根目录的全部分页中选择可预览 README，不改变显式文件定位。
type Entry = { path: string; kind: string; skip_reason?: string | null };
type Page = { items: Entry[]; next_offset: number | null };
const names = ["readme.md", "readme.rst", "readme.txt", "readme"];

export function selectRootReadme(items: Entry[]) {
  const candidates = items.filter(
    (item) =>
      item.kind === "file" &&
      !item.skip_reason &&
      !item.path.includes("/") &&
      names.includes(item.path.toLowerCase()),
  );
  candidates.sort(
    (a, b) =>
      names.indexOf(a.path.toLowerCase()) -
        names.indexOf(b.path.toLowerCase()) ||
      (a.path < b.path ? -1 : a.path > b.path ? 1 : 0),
  );
  return candidates[0]?.path ?? null;
}

export async function loadRootReadme(
  loadPage: (offset: number) => Promise<Page>,
) {
  const items: Entry[] = [];
  let offset = 0;
  while (true) {
    const page = await loadPage(offset);
    items.push(...page.items);
    if (page.next_offset == null) return selectRootReadme(items);
    if (page.next_offset <= offset)
      throw new Error("根目录分页无效，请重新加载");
    offset = page.next_offset;
  }
}
