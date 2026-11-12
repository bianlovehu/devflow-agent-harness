// 文件用途：展示复核意见、停止原因和一次补查轨迹。
import type { components } from "@/lib/generated/api";
import {
  reviewAction,
  reviewStatus,
  reviewTarget,
  supplementRows,
} from "@/lib/review-presentation";

type Review = components["schemas"]["ReportReviewRecord"];

export function ReportReview({ review }: { review?: Review | null }) {
  if (!review) return <p className="hash-note">这份报告没有自动复核记录。</p>;
  return (
    <details className="report-section">
      <summary>模型复核 · {reviewStatus(review.status)}</summary>
      <p>模型意见仅供辅助，重要结论仍需另行核对。</p>
      <p>
        复核请求 {review.review_calls} 次；补查 {review.supplement_rounds}{" "}
        轮；修改 {review.revision_calls} 次。
      </p>
      {review.notes.map((note, index) => (
        <p key={index}>{note}</p>
      ))}
      {review.input_report_sha256 !== review.output_report_sha256 && (
        <p className="source-warning">报告已修改，修改后的内容没有再次复核。</p>
      )}
      <ul>
        {review.decisions.map((decision) => (
          <li key={decision.target}>
            <strong>
              {reviewTarget(decision.target)} · {reviewAction(decision.action)}
            </strong>
            <p>{decision.reason}</p>
            {decision.evidence.length > 0 && (
              <p>
                依据：
                {decision.evidence
                  .map(
                    (c) =>
                      `材料 ${c.evidence_id.slice(0, 8)}，第${c.start_line}—${c.end_line}行`,
                  )
                  .join("；")}
              </p>
            )}
            {decision.metadata_evidence.length > 0 && (
              <p>同时对照了服务端的输入与读取记录。</p>
            )}
          </li>
        ))}
      </ul>
      <details>
        <summary>查看补查记录</summary>
        {supplementRows(review.supplement).map((row, index) => (
          <div key={index}>
            <p>{row.reason}</p>
            {row.error && <p>{row.error}</p>}
            {row.excerpts && <pre>{row.excerpts}</pre>}
          </div>
        ))}
        {!supplementRows(review.supplement).length && (
          <p>
            本次没有补充读取材料；预算不足或没有补查请求时，会保留证据缺口。
          </p>
        )}
      </details>
      <details>
        <summary>查看报告编号</summary>
        <p>修改前：{review.input_report_sha256}</p>
        <p>修改后：{review.output_report_sha256}</p>
      </details>
    </details>
  );
}
