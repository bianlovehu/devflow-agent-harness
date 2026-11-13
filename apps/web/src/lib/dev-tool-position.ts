// 文件用途：限制浮动开发按钮在可见窗口内，适配拖动、尺寸变化和小屏幕。
export function clampDevPosition(
  x: number,
  y: number,
  width: number,
  height: number,
  size: number,
) {
  const safe = (value: number) => (Number.isFinite(value) ? value : 8);
  return {
    x: Math.max(8, Math.min(safe(x), Math.max(8, width - size - 8))),
    y: Math.max(8, Math.min(safe(y), Math.max(8, height - size - 8))),
  };
}
