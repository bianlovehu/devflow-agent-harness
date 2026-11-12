// 文件用途：按事实、推测、建议展示结论，保留原始下标；旧报告不猜测新分类。
import type { components } from "./generated/api";

type Report = components["schemas"]["ReportResponse"]["report"];
type Finding =
  components["schemas"]["Finding"] | components["schemas"]["FindingResultV2"];
type ReportGroup = {
  label: string;
  items: { finding: Finding; index: number }[];
};

export function reportGroups(report: Report): ReportGroup[] {
  if (!("report_version" in report)) {
    return [
      {
        label: "旧版发现（分类未知）",
        items: report.findings.map((finding, index) => ({ finding, index })),
      },
    ];
  }
  return (
    [
      ["fact", "事实（结论尚待复核）"],
      ["hypothesis", "推测（需要补充证据）"],
      ["suggestion", "建议（不计为新增缺陷）"],
    ] as const
  ).map(([nature, label]) => ({
    label,
    items: report.findings.flatMap((finding, index) =>
      finding.nature === nature ? [{ finding, index }] : [],
    ),
  }));
}

export function knownState(value: boolean | null | undefined) {
  return value == null ? "未知" : value ? "是" : "否";
}

export function supportLabel(status?: string) {
  return (
    (
      {
        supported: "证据支持",
        partial: "部分支持，仍需修改",
        unsupported: "证据不支持",
      } as Record<string, string>
    )[status ?? ""] ?? "尚未复核"
  );
}
