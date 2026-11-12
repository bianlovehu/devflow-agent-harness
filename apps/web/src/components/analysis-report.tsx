// 文件用途：展示可定位风险、日志引用、检查范围与 Markdown 评论草稿导出。
"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchData } from "@/lib/api-client";
import {
  knownState,
  reportGroups,
  supportLabel,
} from "@/lib/report-presentation";
import type { components } from "@/lib/generated/api";
import type { ArtifactContent, Evidence, Page, Run } from "@/lib/workflows";
import { QueryState } from "@/components/query-state";
import { ExtractMemory } from "@/components/memory-workspace";
import { ContextHistory } from "@/components/context-history";

type ReportOutput = components["schemas"]["ReportResponse"];
type Citation = components["schemas"]["Citation"];
const severity = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
  info: "提示",
};

function CitationView({
  citation,
  evidence,
  repoId,
}: {
  citation: Citation;
  evidence?: Evidence;
  repoId: string;
}) {
  const [open, setOpen] = useState(false);
  const artifact = useQuery({
    queryKey: ["artifact", repoId, evidence?.artifact_id],
    queryFn: ({ signal }) =>
      fetchData<ArtifactContent>(
        `artifacts/${evidence!.artifact_id}?repo_id=${encodeURIComponent(repoId)}`,
        { signal },
      ),
    enabled: open && Boolean(evidence),
  });
  const lines = artifact.data?.content
    .replace(/\r\n|\r/g, "\n")
    .replace(/\n$/, "")
    .split("\n");
  const start = Math.max(1, citation.start_line - 3);
  return (
    <div className="report-citation">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "收起" : "展开"}{" "}
        {evidence?.source_type === "log" ? "日志" : "证据"} ·{" "}
        {evidence?.path ?? citation.evidence_id} · L{citation.start_line}–
        {citation.end_line}
      </button>
      {open && (
        <div>
          <p className="hash-note">
            {citation.evidence_id} · {evidence?.version}
          </p>
          {!evidence ? (
            <p className="error-message">引用的证据暂不可用，请刷新任务。</p>
          ) : (
            <QueryState
              pending={artifact.isPending}
              error={artifact.error}
              retry={() => void artifact.refetch()}
            />
          )}
          {lines && (
            <div className="code-block evidence-code">
              <ol start={start}>
                {lines
                  .slice(start - 1, citation.end_line + 3)
                  .map((line, i) => (
                    <li
                      key={i}
                      className={
                        start + i >= citation.start_line &&
                        start + i <= citation.end_line
                          ? "evidence-highlight"
                          : ""
                      }
                    >
                      <code>{line || " "}</code>
                    </li>
                  ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AnalysisReport({ run }: { run: Run }) {
  const [exportError, setExportError] = useState("");
  const [copied, setCopied] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const fixedResources = run.input_version.resources;
  const fixedHead = Array.isArray(fixedResources)
    ? (fixedResources[0] as { head_sha?: string } | undefined)?.head_sha
    : undefined;
  const freshness = useQuery({
    queryKey: ["freshness", run.id],
    queryFn: () =>
      fetchData<components["schemas"]["FreshnessResponse"]>(
        `runs/${run.id}/freshness`,
      ),
    enabled: run.task_type === "pr_review",
    refetchOnMount: "always",
  });
  const report = useQuery({
    queryKey: ["report", run.id],
    queryFn: ({ signal }) =>
      fetchData<ReportOutput>(`runs/${run.id}/report`, { signal }),
  });
  const evidence = useQuery({
    queryKey: ["run-evidence", run.id],
    queryFn: ({ signal }) =>
      fetchData<Page<Evidence>>(`runs/${run.id}/evidence`, { signal }),
  });
  function download() {
    if (!report.data) return;
    const url = URL.createObjectURL(
      new Blob([(draft ?? report.data.markdown).replace(/\r?\n/g, "\r\n")], {
        type: "text/markdown;charset=utf-8",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `devflow-${run.task_type}-${run.id.slice(0, 8)}.md`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function copy() {
    if (!report.data) return;
    try {
      await navigator.clipboard.writeText(draft ?? report.data.markdown);
      setCopied(true);
      setExportError("");
    } catch {
      setExportError("复制失败，请下载 Markdown 草稿。");
    }
  }
  const value = report.data?.report;
  return (
    <section className="analysis-report" aria-label="分析报告">
      <p className="eyebrow">分析建议 · 请人工核验后采用</p>
      <p className="column-intro">
        {String(run.result?.provider)} / {String(run.result?.model)} · 模型调用{" "}
        {String(run.result?.model_calls)} 次 · 工具{" "}
        {String(run.result?.tool_calls)} 次
      </p>
      {run.result?.provider === "fake" && (
        <p className="source-warning">
          离线假模型演示；规则输出，未调用真实模型。
        </p>
      )}
      <QueryState
        pending={report.isPending}
        error={report.error}
        retry={() => void report.refetch()}
      />
      {value && (
        <>
          <div className="report-actions">
            <button type="button" onClick={download}>
              下载 Markdown 草稿
            </button>
            <button type="button" onClick={() => void copy()}>
              {copied ? "已复制" : "复制草稿"}
            </button>
          </div>
          <p className="hash-note">
            依据代码版本：
            {String(
              fixedHead ?? run.input_version.repository_commit ?? "见固定输入",
            )}
          </p>
          {run.task_type === "pr_review" && (
            <div
              className={
                freshness.data?.stale ? "source-warning" : "column-intro"
              }
            >
              <p>
                {freshness.data?.note ??
                  (freshness.isPending
                    ? "正在检查 PR 提交…"
                    : "PR 版本未能检查")}
              </p>
              <button
                disabled={freshness.isFetching}
                onClick={() => void freshness.refetch()}
              >
                重新检查 PR 版本
              </button>
              <QueryState
                pending={false}
                error={freshness.error}
                retry={() => void freshness.refetch()}
              />
            </div>
          )}
          <details className="draft-editor">
            <summary>编辑评论草稿</summary>
            <p>修改保存在当前页面，复制和下载均使用编辑后的内容。</p>
            <textarea
              aria-label="评论草稿"
              value={draft ?? report.data?.markdown ?? ""}
              onChange={(event) => {
                setDraft(event.target.value);
                setCopied(false);
              }}
              rows={18}
            />
            <button onClick={() => setDraft(null)}>恢复生成的草稿</button>
          </details>
          {exportError && (
            <p role="alert" className="error-message">
              {exportError}
            </p>
          )}
          <h3>摘要</h3>
          <p className="report-summary">{value.summary}</p>
          {"report_version" in value ? (
            <section className="report-section" aria-label="证据检查与范围">
              <h3>检查状态 · 第2版报告</h3>
              <p>引用检查：通过。来源、行号和读取范围有效。</p>
              <p>
                结论是否被证据支持：
                {supportLabel(value.semantic_support.status)}。
              </p>
              <p>引用有效不代表结论正确。建议不计为新增缺陷。</p>
              <p>
                采集完整：{knownState(value.evidence_facts.collection_complete)}
                ；本次启用知识库：
                {knownState(value.evidence_facts.knowledge_enabled)}。
              </p>
              <p>
                未启用知识库不表示知识库为空。没有采集标记时，原始材料是否截断显示“未知”。
              </p>
              <p>
                本次固定代码版本：
                {value.evidence_facts.current_versions.length
                  ? value.evidence_facts.current_versions
                      .map((v) => String(v.head))
                      .join("、")
                  : "未知"}
              </p>
              {value.evidence_facts.current_versions.some((v) =>
                String(v.version_kind).includes("snapshot"),
              ) && <p>这些是测试生成的版本编号，不能用于远端取代码。</p>}
              <details>
                <summary>查看实际读取范围</summary>
                <ul>
                  {value.evidence_facts.reads.map((item) => (
                    <li key={item.evidence_id}>
                      {item.path}：保存 L{item.stored_start}–{item.stored_end}；
                      已读{" "}
                      {item.read_ranges
                        .map(([start, end]) => `L${start}–${end}`)
                        .join("、") || "尚未读取"}
                      ； 保存内容已读完：{knownState(item.reading_complete)}
                      ；原始材料采集截断：{knownState(item.source_truncated)}。
                    </li>
                  ))}
                </ul>
              </details>
            </section>
          ) : (
            <p className="source-warning">
              旧版报告未记录结论分类、成立前提、严重程度依据和复核状态，这些信息均为未知。
            </p>
          )}
          {value.answer && (
            <section className="report-section">
              <h3>回答</h3>
              <p className="report-summary">{value.answer}</p>
              {value.answer_evidence?.map((citation, i) => (
                <CitationView
                  key={i}
                  citation={citation}
                  evidence={evidence.data?.items.find(
                    (item) => item.id === citation.evidence_id,
                  )}
                  repoId={run.repo_id}
                />
              ))}
              {Boolean(value.answer_evidence?.length) && (
                <ExtractMemory runId={run.id} />
              )}
            </section>
          )}
          {value.failure_stage && (
            <p className="failure-stage">失败阶段：{value.failure_stage}</p>
          )}
          {value.findings.length === 0 && (
            <p className="empty-panel">
              {run.task_type === "knowledge_qa"
                ? "请结合回答、引用和未确认事项核查。"
                : "当前检查范围内未确认风险；仍请核查未确认事项。"}
            </p>
          )}
          <QueryState
            pending={evidence.isPending}
            error={evidence.error}
            retry={() => void evidence.refetch()}
          />
          {reportGroups(value).map((group) => (
            <section key={group.label} className="report-section">
              <h3>
                {group.label} · {group.items.length}
              </h3>
              {!group.items.length && <p>无。</p>}
              {group.items.map(({ finding, index }) => (
                <article
                  key={index}
                  className={`risk-card risk-${finding.severity}`}
                >
                  <div className="risk-heading">
                    <span className="severity-badge">
                      {severity[finding.severity]}
                    </span>
                    <h4>{finding.title}</h4>
                  </div>
                  <p>{finding.explanation}</p>
                  {"nature" in finding ? (
                    <>
                      <p>
                        <strong>共同原因：</strong>
                        {finding.root_cause}
                      </p>
                      <p>
                        <strong>依据：</strong>
                        {finding.basis === "current"
                          ? "本次固定版本"
                          : "历史或背景线索，不能算作本次已确认缺陷"}
                      </p>
                      <p>
                        <strong>直接证据：</strong>
                      </p>
                      {finding.direct_evidence.map((direct, j) => (
                        <div key={j}>
                          <blockquote>{direct.quote}</blockquote>
                          <p>{direct.observation}</p>
                        </div>
                      ))}
                      <p>
                        <strong>成立前提：</strong>
                        {finding.prerequisites.join("；") || "无额外记录"}
                      </p>
                      <p>
                        <strong>还没有确认：</strong>
                        {finding.unconfirmed_conditions.join("；") ||
                          "无额外记录"}
                      </p>
                      <p>
                        <strong>严重程度依据：</strong>
                        {finding.severity_reason}
                      </p>
                      <p>
                        <strong>不同后果：</strong>
                        {finding.consequences.join("；")}
                      </p>
                      <p>
                        <strong>影响范围：</strong>
                        {
                          {
                            local: "仅说明局部代码行为",
                            system: "提供了调用链，是否成立仍待复核",
                            unknown: "未知",
                          }[finding.reachability]
                        }
                      </p>
                      <p>
                        引用检查：通过；结论是否被证据支持：
                        {supportLabel(finding.semantic_support.status)}。
                      </p>
                      {finding.call_chain.length > 0 && (
                        <details>
                          <summary>查看调用链引用</summary>
                          {finding.call_chain.map((citation, j) => (
                            <CitationView
                              key={j}
                              citation={citation}
                              evidence={evidence.data?.items.find(
                                (item) => item.id === citation.evidence_id,
                              )}
                              repoId={run.repo_id}
                            />
                          ))}
                        </details>
                      )}
                    </>
                  ) : (
                    <p>
                      结论性质、直接证据说明、成立前提、未确认条件、严重程度依据：未知（旧版未记录）。
                    </p>
                  )}
                  <p>
                    <strong>建议：</strong>
                    {finding.suggestion}
                  </p>
                  {finding.evidence.map((citation, j) => (
                    <CitationView
                      key={j}
                      citation={citation}
                      evidence={evidence.data?.items.find(
                        (item) => item.id === citation.evidence_id,
                      )}
                      repoId={run.repo_id}
                    />
                  ))}
                  {(!("nature" in finding) ||
                    finding.nature !== "suggestion") && (
                    <ExtractMemory runId={run.id} findingIndex={index} />
                  )}
                </article>
              ))}
            </section>
          ))}
          {(
            [
              ["验证步骤", value.verification_steps],
              [
                run.task_type === "knowledge_qa" ? "补充建议" : "修复建议",
                value.suggestions,
              ],
              ["未确认事项", value.unconfirmed],
              ["检查范围", value.scope],
            ] as const
          ).map(([title, items]) => (
            <section key={title} className="report-section">
              <h3>{title}</h3>
              {items.length ? (
                <ul>
                  {items.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p>无补充内容。</p>
              )}
            </section>
          ))}
          <details>
            <summary>模型用量</summary>
            <pre>{JSON.stringify(run.result?.usage, null, 2)}</pre>
          </details>
          <ContextHistory runId={run.id} />
        </>
      )}
    </section>
  );
}
