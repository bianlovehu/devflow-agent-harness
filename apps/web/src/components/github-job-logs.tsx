// 文件用途：仅在用户选择 job 后读取日志，并展示未就绪或过期错误。
"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchData } from "@/lib/api-client";
import type { CIRunDetail, JobLog } from "@/lib/repositories";
import { ciStatus } from "@/lib/ci-status";
import { QueryState } from "@/components/query-state";

export function GitHubJobLogs({ run }: { run: CIRunDetail }) {
  const [selected, setSelected] = useState<number>();
  const query = useQuery({
    queryKey: [
      "github-job-log",
      run.repo_id,
      run.id,
      selected,
      run.run_attempt,
    ],
    queryFn: ({ signal }) =>
      fetchData<JobLog>(
        `repositories/${run.repo_id}/ci-runs/${run.id}/jobs/${selected}/logs`,
        { signal },
      ),
    enabled: selected !== undefined,
    retry: false,
  });
  const lines =
    query.data?.content.replace(/\r\n/g, "\n").trimEnd().split("\n") ?? [];
  return (
    <section className="github-jobs">
      <h3>Jobs 与步骤</h3>
      {run.jobs_limited && (
        <p className="source-warnings">job列表达到读取上限，当前结果不完整。</p>
      )}
      {(run.jobs ?? []).length === 0 && (
        <p className="column-intro">该运行暂未返回job。</p>
      )}
      {(run.jobs ?? []).map((job) => {
        const state = ciStatus(job);
        return (
          <article className="github-job" key={job.id}>
            <div>
              <h4>{job.name}</h4>
              <span className={`ci-state ${state.tone}`}>{state.label}</span>
            </div>
            <details>
              <summary>查看执行步骤</summary>
              <ol>
                {(job.steps ?? []).map((step) => (
                  <li key={step.number}>
                    {step.name} <span>{ciStatus(step).label}</span>
                  </li>
                ))}
              </ol>
            </details>
            <button
              type="button"
              disabled={job.status !== "completed" || query.isFetching}
              onClick={() => setSelected(job.id)}
            >
              {job.status === "completed"
                ? "读取此 job 日志"
                : "job完成后可读日志"}
            </button>
          </article>
        );
      })}
      {selected !== undefined && (
        <section className="github-log-preview">
          <h4>Job #{selected} 日志</h4>
          <QueryState
            pending={query.isPending}
            error={query.error}
            retry={() => void query.refetch()}
          />
          {query.data && (
            <>
              <p className="fetch-info">
                获取于{" "}
                {new Date(query.data.fetched_at).toLocaleString("zh-CN", {
                  hour12: false,
                })}
              </p>
              {lines.length > 2000 && (
                <p className="source-warnings">
                  日志较长，页面仅预览前2000行。
                </p>
              )}
              <div className="code-block">
                <ol>
                  {lines.slice(0, 2000).map((line, index) => (
                    <li key={index}>
                      <code>{line || " "}</code>
                    </li>
                  ))}
                </ol>
              </div>
              <p className="hash-note">
                预览内容 SHA256 <code>{query.data.content_sha256}</code>
              </p>
            </>
          )}
        </section>
      )}
    </section>
  );
}
