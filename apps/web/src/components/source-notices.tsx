// 文件用途：展示来源抓取时间、同步范围和不完整数据提示。
import type { SourceNotice } from "@/lib/repositories";
export function SourceNotices({ notices }: { notices?: SourceNotice[] }) {
  if (!notices?.length) return null;
  return (
    <div className="source-warnings" role="status">
      {notices.map((notice, index) => (
        <p key={`${notice.code}:${index}`}>
          {notice.message}
          {notice.retry_after ? `，建议至少等待 ${notice.retry_after} 秒` : ""}
          <small>{notice.code}</small>
        </p>
      ))}
    </div>
  );
}
export function FetchInfo({
  at,
  limited,
}: {
  at?: string | null;
  limited?: boolean;
}) {
  if (!at && !limited) return null;
  return (
    <p className="fetch-info">
      {at &&
        `获取于 ${new Date(at).toLocaleString("zh-CN", { hour12: false })}`}
      {limited && " · 当前仅显示已同步的有限记录，未覆盖全部资源"}
    </p>
  );
}
