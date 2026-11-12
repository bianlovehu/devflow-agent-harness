// 文件用途：提供统一的单色线框图标。
import type { CSSProperties } from "react";

const paths = {
  panel:
    "M9 3v18M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1",
  plus: "M12 5v14M5 12h14",
  chat: "M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 1 1 19 0Z",
  repo: "m8 5-7 7 7 7m8-14 7 7-7 7m-3-17-2 20",
  book: "M12 5c-3-2-7-2-10-1v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Zm0 0v15",
  memory: "m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  chevron: "m6 9 6 6 6-6",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  up: "M12 19V5m-6 6 6-6 6 6",
  close: "m6 6 12 12M6 18 18 6",
  refresh: "M20 7a9 9 0 1 0 1 8M20 2v6h-6",
  file: "M14 2H5v20h14V7Zm0 0v6h5M8 12h8m-8 4h8",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  external: "M14 3h7v7m0-7L10 14M10 3H3v18h18v-7",
  check: "m5 12 4 4L20 5",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  settings: "M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6m-7 0v6",
  home: "m3 10 9-8 9 8v11h-7v-7h-4v7H3Z",
} as const;

export function Icon({
  name,
  size = 20,
  style,
}: {
  name: keyof typeof paths;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      <path d={paths[name]} />
    </svg>
  );
}

export function DevFlowMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M16 1c2.2 9.3 5.7 12.8 15 15-9.3 2.2-12.8 5.7-15 15C13.8 21.7 10.3 18.2 1 16 10.3 13.8 13.8 10.3 16 1Z" />
    </svg>
  );
}
