// 文件用途：按任务事件序号合并历史和实时记录，拒绝跨任务事件并保留连续续传位置。
export type SequencedEvent = { run_id: string; sequence: number };

export function mergeEvents<T extends SequencedEvent>(
  runId: string,
  before: T[],
  incoming: T[],
): T[] {
  const rows = new Map<number, T>();
  for (const item of [...before, ...incoming])
    if (
      item.run_id === runId &&
      Number.isSafeInteger(item.sequence) &&
      item.sequence > 0
    )
      rows.set(item.sequence, item);
  return [...rows.values()].sort((a, b) => a.sequence - b.sequence);
}

export function contiguousCursor(rows: SequencedEvent[]): number {
  let cursor = 0;
  for (const row of rows) {
    if (row.sequence === cursor + 1) cursor++;
    else if (row.sequence > cursor + 1) break;
  }
  return cursor;
}
