// 文件用途：将报告引用定位到对应任务的证据面板，外部单独渲染报告时保留内联预览。
"use client";
import { createContext } from "react";
export type EvidenceLocation = {
  runId: string;
  evidenceId?: string;
  start?: number;
  end?: number;
};
export const EvidenceNavigation = createContext<
  ((location: EvidenceLocation) => void) | null
>(null);
