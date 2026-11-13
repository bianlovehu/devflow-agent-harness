// 文件用途：保存从 FastAPI OpenAPI 自动生成的接口类型，请勿手工修改。
export interface paths {
  "/api/v1/artifacts/{artifact_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Artifact */
    get: operations["artifact_api_v1_artifacts__artifact_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/budget": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Summary */
    get: operations["summary_api_v1_budget_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/conversations": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Conversations */
    get: operations["conversations_api_v1_conversations_get"];
    put?: never;
    /** Post Conversation */
    post: operations["post_conversation_api_v1_conversations_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/conversations/{conversation_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Conversation */
    get: operations["conversation_api_v1_conversations__conversation_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/conversations/{conversation_id}/messages": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Messages */
    get: operations["messages_api_v1_conversations__conversation_id__messages_get"];
    put?: never;
    /** Post Message */
    post: operations["post_message_api_v1_conversations__conversation_id__messages_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/health": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Health */
    get: operations["health_api_v1_health_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/health/live": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Liveness */
    get: operations["liveness_api_v1_health_live_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/knowledge": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Documents */
    get: operations["documents_api_v1_knowledge_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/knowledge/search": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Search */
    post: operations["search_api_v1_knowledge_search_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/knowledge/status": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Status */
    get: operations["status_api_v1_knowledge_status_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/knowledge/upload": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Upload */
    post: operations["upload_api_v1_knowledge_upload_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/knowledge/{document_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Detail */
    get: operations["detail_api_v1_knowledge__document_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/knowledge/{document_id}/delete": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Remove */
    post: operations["remove_api_v1_knowledge__document_id__delete_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/knowledge/{document_id}/versions/{version_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Preview */
    get: operations["preview_api_v1_knowledge__document_id__versions__version_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/memories": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Memories */
    get: operations["memories_api_v1_memories_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/memories/search": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Search */
    post: operations["search_api_v1_memories_search_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/memories/{memory_id}/approve": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Approve */
    post: operations["approve_api_v1_memories__memory_id__approve_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/memories/{memory_id}/edit": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Edit */
    post: operations["edit_api_v1_memories__memory_id__edit_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/memories/{memory_id}/index": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Reindex */
    post: operations["reindex_api_v1_memories__memory_id__index_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/memories/{memory_id}/revoke": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Revoke */
    post: operations["revoke_api_v1_memories__memory_id__revoke_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Repositories */
    get: operations["repositories_api_v1_repositories_get"];
    put?: never;
    /** Add Repository */
    post: operations["add_repository_api_v1_repositories_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Repository */
    get: operations["repository_api_v1_repositories__repo_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/ci-runs": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Ci Runs */
    get: operations["ci_runs_api_v1_repositories__repo_id__ci_runs_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/ci-runs/{run_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Ci Run */
    get: operations["ci_run_api_v1_repositories__repo_id__ci_runs__run_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/ci-runs/{run_id}/jobs/{job_id}/logs": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Job Logs */
    get: operations["job_logs_api_v1_repositories__repo_id__ci_runs__run_id__jobs__job_id__logs_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/documents": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Documents */
    get: operations["documents_api_v1_repositories__repo_id__documents_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/documents/{document_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Document */
    get: operations["document_api_v1_repositories__repo_id__documents__document_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/pull-requests": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Pull Requests */
    get: operations["pull_requests_api_v1_repositories__repo_id__pull_requests_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/pull-requests/{number}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Pull Request */
    get: operations["pull_request_api_v1_repositories__repo_id__pull_requests__number__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/repositories/{repo_id}/refresh": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Refresh Repository */
    post: operations["refresh_repository_api_v1_repositories__repo_id__refresh_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Runs */
    get: operations["runs_api_v1_runs_get"];
    put?: never;
    /** Post Run */
    post: operations["post_run_api_v1_runs_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Run */
    get: operations["run_api_v1_runs__run_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/artifacts": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Artifacts */
    get: operations["artifacts_api_v1_runs__run_id__artifacts_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/cancel": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Post Cancel */
    post: operations["post_cancel_api_v1_runs__run_id__cancel_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/context": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Context History */
    get: operations["context_history_api_v1_runs__run_id__context_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/cost": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Run Cost */
    get: operations["run_cost_api_v1_runs__run_id__cost_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/events": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Events */
    get: operations["events_api_v1_runs__run_id__events_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/evidence": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Evidence */
    get: operations["evidence_api_v1_runs__run_id__evidence_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/freshness": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Freshness */
    get: operations["freshness_api_v1_runs__run_id__freshness_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/memories": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Extract */
    post: operations["extract_api_v1_runs__run_id__memories_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/memories/revoke-source": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Revoke Source */
    post: operations["revoke_source_api_v1_runs__run_id__memories_revoke_source_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/report": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Report */
    get: operations["report_api_v1_runs__run_id__report_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/retry": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Post Retry */
    post: operations["post_retry_api_v1_runs__run_id__retry_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runs/{run_id}/stream": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Run Stream */
    get: operations["run_stream_api_v1_runs__run_id__stream_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/runtime": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Runtime */
    get: operations["runtime_api_v1_runtime_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /** AnalysisReport */
    AnalysisReport: {
      /** Answer */
      answer?: string | null;
      /** Answer Evidence */
      answer_evidence?: components["schemas"]["Citation"][];
      /** Failure Stage */
      failure_stage?: string | null;
      /** Findings */
      findings: components["schemas"]["Finding"][];
      /** Scope */
      scope: string[];
      /** Suggestions */
      suggestions: string[];
      /** Summary */
      summary: string;
      /**
       * Task Type
       * @enum {string}
       */
      task_type: "pr_review" | "ci_debug" | "knowledge_qa";
      /** Unconfirmed */
      unconfirmed: string[];
      /** Verification Steps */
      verification_steps: string[];
    };
    /** ArtifactContent */
    ArtifactContent: {
      artifact: components["schemas"]["ArtifactResponse"];
      /** Content */
      content: string;
    };
    /** ArtifactResponse */
    ArtifactResponse: {
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Media Type */
      media_type: string;
      /** Repo Id */
      repo_id: string;
      /** Sha256 */
      sha256: string;
      /** Size Bytes */
      size_bytes: number;
    };
    /** BoundaryClaim */
    BoundaryClaim: {
      /**
       * Evidence Id
       * Format: uuid
       */
      evidence_id: string;
      /**
       * Kind
       * @enum {string}
       */
      kind: "source_truncated" | "reading_incomplete";
    };
    /** BudgetResponse */
    BudgetResponse: {
      /** Available Cny */
      available_cny: string;
      /** Basis */
      basis: string;
      /**
       * Currency
       * @constant
       */
      currency: "CNY";
      /** Limits */
      limits: {
        [key: string]: number;
      };
      /** Reserved Cny */
      reserved_cny: string;
      /** Settled Cny */
      settled_cny: string;
      /**
       * Status
       * @enum {string}
       */
      status: "ok" | "warning" | "blocked";
      /** Stop Cny */
      stop_cny: string;
      /** Total Cny */
      total_cny: string;
      /** Tracked */
      tracked: boolean;
      /** Unknown Requests */
      unknown_requests: number;
      /** Warning Cny */
      warning_cny: string;
    };
    /** CIJob */
    CIJob: {
      /** Completed At */
      completed_at?: string | null;
      /** Conclusion */
      conclusion: string | null;
      /** Id */
      id: number;
      /** Name */
      name: string;
      /** Run Id */
      run_id: number;
      /** Started At */
      started_at?: string | null;
      /** Status */
      status: string;
      /** Steps */
      steps?: components["schemas"]["CIStep"][];
    };
    /** CIRunDetail */
    CIRunDetail: {
      /** Conclusion */
      conclusion: string | null;
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /** Duration Seconds */
      duration_seconds: number | null;
      /** Fetched At */
      fetched_at?: string | null;
      /** Head Sha */
      head_sha: string;
      /** Html Url */
      html_url?: string | null;
      /** Id */
      id: number;
      /** Jobs */
      jobs?: components["schemas"]["CIJob"][];
      /**
       * Jobs Limited
       * @default false
       */
      jobs_limited: boolean;
      /** Log */
      log?: string | null;
      /** Log Sha256 */
      log_sha256?: string | null;
      /** Name */
      name: string;
      /** Pull Request Number */
      pull_request_number: number | null;
      /** Repo Id */
      repo_id: string;
      /**
       * Run Attempt
       * @default 1
       */
      run_attempt: number;
      /** Stage */
      stage: ("install" | "test" | "configure") | null;
      /**
       * Started At
       * Format: date-time
       */
      started_at: string;
      /**
       * Status
       * @default completed
       */
      status: string;
      /** Warnings */
      warnings?: components["schemas"]["SourceNotice"][];
    };
    /** CIRunSummary */
    CIRunSummary: {
      /** Conclusion */
      conclusion: string | null;
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /** Duration Seconds */
      duration_seconds: number | null;
      /** Fetched At */
      fetched_at?: string | null;
      /** Head Sha */
      head_sha: string;
      /** Html Url */
      html_url?: string | null;
      /** Id */
      id: number;
      /** Name */
      name: string;
      /** Pull Request Number */
      pull_request_number: number | null;
      /** Repo Id */
      repo_id: string;
      /**
       * Run Attempt
       * @default 1
       */
      run_attempt: number;
      /** Stage */
      stage: ("install" | "test" | "configure") | null;
      /**
       * Started At
       * Format: date-time
       */
      started_at: string;
      /**
       * Status
       * @default completed
       */
      status: string;
    };
    /** CIStep */
    CIStep: {
      /** Conclusion */
      conclusion?: string | null;
      /** Name */
      name: string;
      /** Number */
      number: number;
      /** Status */
      status: string;
    };
    /** ChangedFile */
    ChangedFile: {
      /** Additions */
      additions: number;
      /** Base Content */
      base_content?: string | null;
      /** Content Sha256 */
      content_sha256?: string | null;
      /** Deletions */
      deletions: number;
      /** Head Content */
      head_content?: string | null;
      /** Patch */
      patch: string;
      /**
       * Patch Available
       * @default true
       */
      patch_available: boolean;
      /** Path */
      path: string;
      /** Previous Path */
      previous_path?: string | null;
      /**
       * Status
       * @default modified
       */
      status: string;
    };
    /** Citation */
    Citation: {
      /** End Line */
      end_line: number;
      /**
       * Evidence Id
       * Format: uuid
       */
      evidence_id: string;
      /** Start Line */
      start_line: number;
    };
    /** Collection[CIRunSummary] */
    Collection_CIRunSummary_: {
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github" | "mixed";
      /** Fetched At */
      fetched_at?: string | null;
      /** Items */
      items: components["schemas"]["CIRunSummary"][];
      /**
       * Limited
       * @default false
       */
      limited: boolean;
      /** Warnings */
      warnings?: components["schemas"]["SourceNotice"][];
    };
    /** Collection[DocumentSummary] */
    Collection_DocumentSummary_: {
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github" | "mixed";
      /** Fetched At */
      fetched_at?: string | null;
      /** Items */
      items: components["schemas"]["DocumentSummary"][];
      /**
       * Limited
       * @default false
       */
      limited: boolean;
      /** Warnings */
      warnings?: components["schemas"]["SourceNotice"][];
    };
    /** Collection[PullRequestSummary] */
    Collection_PullRequestSummary_: {
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github" | "mixed";
      /** Fetched At */
      fetched_at?: string | null;
      /** Items */
      items: components["schemas"]["PullRequestSummary"][];
      /**
       * Limited
       * @default false
       */
      limited: boolean;
      /** Warnings */
      warnings?: components["schemas"]["SourceNotice"][];
    };
    /** Collection[Repository] */
    Collection_Repository_: {
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github" | "mixed";
      /** Fetched At */
      fetched_at?: string | null;
      /** Items */
      items: components["schemas"]["Repository"][];
      /**
       * Limited
       * @default false
       */
      limited: boolean;
      /** Warnings */
      warnings?: components["schemas"]["SourceNotice"][];
    };
    /** ComponentHealth */
    ComponentHealth: {
      /** Message */
      message: string;
      /**
       * Status
       * @enum {string}
       */
      status: "ok" | "error" | "pending" | "unknown";
      /** Version */
      version?: string | null;
    };
    /** ContextResponse */
    ContextResponse: {
      /** Calls */
      calls: {
        [key: string]: unknown;
      }[];
      /** Recovery Count */
      recovery_count: number;
    };
    /** ConversationCreate */
    ConversationCreate: {
      /** Repo Id */
      repo_id: string;
      /** Title */
      title: string;
    };
    /** ConversationResponse */
    ConversationResponse: {
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Repo Id */
      repo_id: string;
      /** Title */
      title: string;
    };
    /** CostResponse */
    CostResponse: {
      /** Requests */
      requests: {
        [key: string]: unknown;
      }[];
      /** Reserved Cny */
      reserved_cny: string;
      /** Settled Cny */
      settled_cny: string;
      /** Tracked */
      tracked: boolean;
      /** Unknown Requests */
      unknown_requests: number;
    };
    /** DirectEvidence */
    DirectEvidence: {
      citation: components["schemas"]["Citation"];
      /** Observation */
      observation: string;
      /** Quote */
      quote: string;
    };
    /** DocumentDetail */
    DocumentDetail: {
      /** Content */
      content: string;
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /** Id */
      id: string;
      /**
       * Kind
       * @enum {string}
       */
      kind: "architecture" | "policy" | "runbook" | "postmortem";
      /** Line Count */
      line_count: number;
      /** Repo Id */
      repo_id: string;
      /** Title */
      title: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /** Version */
      version: string;
    };
    /** DocumentSummary */
    DocumentSummary: {
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /** Id */
      id: string;
      /**
       * Kind
       * @enum {string}
       */
      kind: "architecture" | "policy" | "runbook" | "postmortem";
      /** Line Count */
      line_count: number;
      /** Repo Id */
      repo_id: string;
      /** Title */
      title: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /** Version */
      version: string;
    };
    /** EventPage */
    EventPage: {
      /** Items */
      items: components["schemas"]["RunEventResponse"][];
      /** Next After */
      next_after?: number | null;
    };
    /** EvidenceFacts */
    EvidenceFacts: {
      /** Collection Complete */
      collection_complete: boolean | null;
      /** Current Versions */
      current_versions: {
        [key: string]: unknown;
      }[];
      /** Knowledge Enabled */
      knowledge_enabled: boolean | null;
      /** Reads */
      reads: components["schemas"]["ReadState"][];
    };
    /** EvidenceResponse */
    EvidenceResponse: {
      /**
       * Artifact Id
       * Format: uuid
       */
      artifact_id: string;
      /** End Line */
      end_line: number;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Path */
      path: string;
      /** Repo Id */
      repo_id: string;
      /**
       * Resource Snapshot Id
       * Format: uuid
       */
      resource_snapshot_id: string;
      /**
       * Retrieved At
       * Format: date-time
       */
      retrieved_at: string;
      /** Source Type */
      source_type: string;
      /** Start Line */
      start_line: number;
      /** Version */
      version: string;
    };
    /** Finding */
    Finding: {
      /** Evidence */
      evidence: components["schemas"]["Citation"][];
      /** Explanation */
      explanation: string;
      /**
       * Severity
       * @enum {string}
       */
      severity: "critical" | "high" | "medium" | "low" | "info";
      /** Suggestion */
      suggestion: string;
      /** Title */
      title: string;
    };
    /** FindingResultV2 */
    FindingResultV2: {
      /**
       * Basis
       * @enum {string}
       */
      basis: "current" | "reference";
      /** Call Chain */
      call_chain: components["schemas"]["Citation"][];
      /**
       * Citation Check
       * @constant
       */
      citation_check: "passed";
      /**
       * Claim Type
       * @enum {string}
       */
      claim_type:
        "code_behavior" | "run_result" | "document_statement" | "follow_up";
      /** Consequences */
      consequences: string[];
      /** Direct Evidence */
      direct_evidence: components["schemas"]["DirectEvidence"][];
      /** Evidence */
      evidence: components["schemas"]["Citation"][];
      /** Explanation */
      explanation: string;
      /**
       * Nature
       * @enum {string}
       */
      nature: "fact" | "hypothesis" | "suggestion";
      /** Prerequisites */
      prerequisites: string[];
      /**
       * Reachability
       * @enum {string}
       */
      reachability: "local" | "system" | "unknown";
      /** Root Cause */
      root_cause: string;
      semantic_support: components["schemas"]["SemanticReview"];
      /**
       * Severity
       * @enum {string}
       */
      severity: "critical" | "high" | "medium" | "low" | "info";
      /** Severity Reason */
      severity_reason: string;
      /** Suggestion */
      suggestion: string;
      /** Title */
      title: string;
      /** Unconfirmed Conditions */
      unconfirmed_conditions: string[];
    };
    /** FreshnessResponse */
    FreshnessResponse: {
      /** Analyzed Head */
      analyzed_head: string | null;
      /** Checked */
      checked: boolean;
      /** Current Head */
      current_head: string | null;
      /** Note */
      note: string;
      /** Stale */
      stale: boolean | null;
    };
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components["schemas"]["ValidationError"][];
    };
    /** HealthResponse */
    HealthResponse: {
      /**
       * Checked At
       * Format: date-time
       */
      checked_at: string;
      /** Checks */
      checks: {
        [key: string]: components["schemas"]["ComponentHealth"];
      };
      /**
       * Service
       * @default devflow-api
       */
      service: string;
      /**
       * Status
       * @enum {string}
       */
      status: "ok" | "degraded";
      /**
       * Version
       * @default 0.1.0
       */
      version: string;
    };
    /** JobLog */
    JobLog: {
      /** Content */
      content: string;
      /** Content Sha256 */
      content_sha256: string;
      /**
       * Fetched At
       * Format: date-time
       */
      fetched_at: string;
      /** Job Id */
      job_id: number;
      /** Repo Id */
      repo_id: string;
      /** Run Id */
      run_id: number;
    };
    /** KnowledgeDetail */
    KnowledgeDetail: {
      document: components["schemas"]["KnowledgeDocumentOutput"];
      /** Versions */
      versions: components["schemas"]["KnowledgeVersionOutput"][];
    };
    /** KnowledgeDocumentOutput */
    KnowledgeDocumentOutput: {
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Deleted */
      deleted: boolean;
      /** Filename */
      filename: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Repo Id */
      repo_id: string;
      /** Source */
      source: string;
    };
    /** KnowledgePreview */
    KnowledgePreview: {
      /** Content */
      content: string | null;
      /** Page Starts */
      page_starts: {
        [key: string]: unknown;
      }[];
      version: components["schemas"]["KnowledgeVersionOutput"];
    };
    /** KnowledgeSearch */
    KnowledgeSearch: {
      /**
       * Limit
       * @default 6
       */
      limit: number;
      /**
       * Mode
       * @default hybrid
       * @enum {string}
       */
      mode: "hybrid" | "keyword";
      /** Query */
      query: string;
      /** Repo Id */
      repo_id: string;
    };
    /** KnowledgeSearchHit */
    KnowledgeSearchHit: {
      /**
       * Chunk Id
       * Format: uuid
       */
      chunk_id: string;
      /** Content */
      content: string;
      /**
       * Document Id
       * Format: uuid
       */
      document_id: string;
      /** End Line */
      end_line: number;
      /**
       * Evidence Id
       * Format: uuid
       */
      evidence_id: string;
      /** Filename */
      filename: string;
      /** Page */
      page: number | null;
      /** Ranks */
      ranks: {
        [key: string]: number;
      };
      /** Rrf Score */
      rrf_score: number;
      /** Source */
      source: string;
      /** Start Line */
      start_line: number;
      /** Token Count */
      token_count: number;
      /** Vector Similarity */
      vector_similarity: number | null;
      /**
       * Version Id
       * Format: uuid
       */
      version_id: string;
      /** Version Number */
      version_number: number;
    };
    /** KnowledgeSearchOutput */
    KnowledgeSearchOutput: {
      /** Items */
      items: components["schemas"]["KnowledgeSearchHit"][];
      /**
       * Mode
       * @enum {string}
       */
      mode: "hybrid" | "keyword";
      /** Model Key */
      model_key: string;
      /** Note */
      note: string;
    };
    /** KnowledgeUpload */
    KnowledgeUpload: {
      /** Content Base64 */
      content_base64: string;
      /** Filename */
      filename: string;
      /** Repo Id */
      repo_id: string;
    };
    /** KnowledgeUploadOutput */
    KnowledgeUploadOutput: {
      /**
       * Document Id
       * Format: uuid
       */
      document_id: string;
      /** Duplicate */
      duplicate: boolean;
      version: components["schemas"]["KnowledgeVersionOutput"];
    };
    /** KnowledgeVersionOutput */
    KnowledgeVersionOutput: {
      /** Chunk Count */
      chunk_count: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Error Code */
      error_code: string | null;
      /** Error Message */
      error_message: string | null;
      /** Evidence Id */
      evidence_id: string | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Is Current */
      is_current: boolean;
      /** Model Key */
      model_key: string | null;
      /** Number */
      number: number;
      /** Raw Sha256 */
      raw_sha256: string;
      /** Size Bytes */
      size_bytes: number;
      /**
       * Status
       * @enum {string}
       */
      status: "indexing" | "ready" | "failed";
    };
    /** LinkedIssue */
    LinkedIssue: {
      /** Body */
      body: string;
      /** Html Url */
      html_url: string;
      /** Number */
      number: number;
      /**
       * Relation
       * @default body_reference
       * @constant
       */
      relation: "body_reference";
      /** State */
      state: string;
      /** Title */
      title: string;
    };
    /** MemoryApprove */
    MemoryApprove: {
      /** Replaces Id */
      replaces_id?: string | null;
      /** Reviewed Conflicts */
      reviewed_conflicts?: {
        [key: string]: number;
      };
    };
    /** MemoryEdit */
    MemoryEdit: {
      /** Applicable Version */
      applicable_version?: string | null;
      /**
       * Conditions
       * @default
       */
      conditions: string;
      /** Expires At */
      expires_at?: string | null;
      /** Summary */
      summary: string;
    };
    /** MemoryExtract */
    MemoryExtract: {
      /** Finding Index */
      finding_index?: number | null;
    };
    /** MemoryOutput */
    MemoryOutput: {
      /** Applicable Version */
      applicable_version: string | null;
      /** Approved At */
      approved_at: string | null;
      /** Conditions */
      conditions: string;
      /** Conflict Reviews */
      conflict_reviews: {
        [key: string]: unknown;
      };
      /** Conflicts */
      conflicts?: {
        [key: string]: unknown;
      }[];
      /** Content Revision */
      content_revision: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Embedding Model */
      embedding_model: string | null;
      /** Embedding Revision */
      embedding_revision: number | null;
      /**
       * Expired
       * @default false
       */
      expired: boolean;
      /**
       * Expires At
       * Format: date-time
       */
      expires_at: string;
      /** Extraction */
      extraction: {
        [key: string]: unknown;
      };
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Index Current
       * @default false
       */
      index_current: boolean;
      /** Index Error */
      index_error: string | null;
      /** Index Status */
      index_status: string;
      /** Indexed At */
      indexed_at: string | null;
      /** Replaces Id */
      replaces_id: string | null;
      /** Repo Id */
      repo_id: string;
      /** Selection */
      selection: string;
      /**
       * Source Run Id
       * Format: uuid
       */
      source_run_id: string;
      /** Sources */
      sources: {
        [key: string]: unknown;
      }[];
      /**
       * Status
       * @enum {string}
       */
      status: "pending" | "approved" | "revoked" | "superseded";
      /** Summary */
      summary: string;
    };
    /** MemorySearch */
    MemorySearch: {
      /** Query */
      query: string;
      /** Repo Id */
      repo_id: string;
      /** Version */
      version?: string | null;
    };
    /** MessageCreate */
    MessageCreate: {
      /** Content */
      content: string;
    };
    /** MessageResponse */
    MessageResponse: {
      /** Content */
      content: string;
      /**
       * Conversation Id
       * Format: uuid
       */
      conversation_id: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Role
       * @enum {string}
       */
      role: "user" | "assistant" | "system";
      /** Sequence */
      sequence: number;
    };
    /** ModelInfo */
    ModelInfo: {
      /** Configured */
      configured: boolean;
      /** Name */
      name: string;
      /** Provider */
      provider: string;
    };
    /** Page[ArtifactResponse] */
    Page_ArtifactResponse_: {
      /** Items */
      items: components["schemas"]["ArtifactResponse"][];
      /** Next Offset */
      next_offset?: number | null;
    };
    /** Page[ConversationResponse] */
    Page_ConversationResponse_: {
      /** Items */
      items: components["schemas"]["ConversationResponse"][];
      /** Next Offset */
      next_offset?: number | null;
    };
    /** Page[EvidenceResponse] */
    Page_EvidenceResponse_: {
      /** Items */
      items: components["schemas"]["EvidenceResponse"][];
      /** Next Offset */
      next_offset?: number | null;
    };
    /** Page[KnowledgeDocumentOutput] */
    Page_KnowledgeDocumentOutput_: {
      /** Items */
      items: components["schemas"]["KnowledgeDocumentOutput"][];
      /** Next Offset */
      next_offset?: number | null;
    };
    /** Page[MemoryOutput] */
    Page_MemoryOutput_: {
      /** Items */
      items: components["schemas"]["MemoryOutput"][];
      /** Next Offset */
      next_offset?: number | null;
    };
    /** Page[MessageResponse] */
    Page_MessageResponse_: {
      /** Items */
      items: components["schemas"]["MessageResponse"][];
      /** Next Offset */
      next_offset?: number | null;
    };
    /** Page[RunResponse] */
    Page_RunResponse_: {
      /** Items */
      items: components["schemas"]["RunResponse"][];
      /** Next Offset */
      next_offset?: number | null;
    };
    /** PullRequestDetail */
    PullRequestDetail: {
      /** Author */
      author: string;
      /** Base Sha */
      base_sha: string;
      /** Body */
      body: string;
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /** Fetched At */
      fetched_at?: string | null;
      /** Files */
      files: components["schemas"]["ChangedFile"][];
      /**
       * Files Limited
       * @default false
       */
      files_limited: boolean;
      /** Head Sha */
      head_sha: string;
      /** Html Url */
      html_url?: string | null;
      /** Linked Issues */
      linked_issues?: components["schemas"]["LinkedIssue"][];
      /** Number */
      number: number;
      /** Repo Id */
      repo_id: string;
      /**
       * State
       * @enum {string}
       */
      state: "open" | "closed" | "merged";
      /** Title */
      title: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /** Warnings */
      warnings?: components["schemas"]["SourceNotice"][];
    };
    /** PullRequestSummary */
    PullRequestSummary: {
      /** Author */
      author: string;
      /** Base Sha */
      base_sha: string;
      /** Body */
      body: string;
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /** Fetched At */
      fetched_at?: string | null;
      /** Head Sha */
      head_sha: string;
      /** Html Url */
      html_url?: string | null;
      /** Number */
      number: number;
      /** Repo Id */
      repo_id: string;
      /**
       * State
       * @enum {string}
       */
      state: "open" | "closed" | "merged";
      /** Title */
      title: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /** ReadState */
    ReadState: {
      /**
       * Evidence Id
       * Format: uuid
       */
      evidence_id: string;
      /** Path */
      path: string;
      /** Read Ranges */
      read_ranges: [number, number][];
      /** Reading Complete */
      reading_complete: boolean;
      /** Source Truncated */
      source_truncated: boolean | null;
      /** Stored End */
      stored_end: number;
      /** Stored Start */
      stored_start: number;
    };
    /** ReportResponse */
    ReportResponse: {
      /** Markdown */
      markdown: string;
      /** Report */
      report:
        | components["schemas"]["AnalysisReport"]
        | components["schemas"]["ReportV2"];
      review?: components["schemas"]["ReportReviewRecord"] | null;
    };
    /** ReportReviewRecord */
    ReportReviewRecord: {
      /** Decisions */
      decisions: components["schemas"]["ReviewDecision"][];
      /** Deterministic */
      deterministic: {
        [key: string]: unknown;
      };
      /** Initial Duration Ms */
      initial_duration_ms: number;
      /** Initial Observed */
      initial_observed: {
        [key: string]: unknown;
      };
      initial_report: components["schemas"]["ReportV2"];
      /** Initial Tool Calls */
      initial_tool_calls?: number | null;
      /** Initial Usage */
      initial_usage: {
        [key: string]: unknown;
      };
      /** Input Report Sha256 */
      input_report_sha256: string;
      /** Notes */
      notes: string[];
      /** Output Report Sha256 */
      output_report_sha256: string;
      /** Review Calls */
      review_calls: number;
      /** Revision */
      revision: {
        [key: string]: unknown;
      };
      /** Revision Calls */
      revision_calls: number;
      /** Status */
      status: string;
      /** Supplement */
      supplement: {
        [key: string]: unknown;
      };
      /** Supplement Rounds */
      supplement_rounds: number;
      /** Triggers */
      triggers: string[];
      /** Version */
      version: string;
    };
    /** ReportV2 */
    ReportV2: {
      /** Answer */
      answer?: string | null;
      /** Answer Evidence */
      answer_evidence?: components["schemas"]["Citation"][];
      /** Boundary Claims */
      boundary_claims: components["schemas"]["BoundaryClaim"][];
      /**
       * Citation Check
       * @constant
       */
      citation_check: "passed";
      evidence_facts: components["schemas"]["EvidenceFacts"];
      /** Failure Stage */
      failure_stage?: string | null;
      /** Findings */
      findings: components["schemas"]["FindingResultV2"][];
      /**
       * Report Version
       * @constant
       */
      report_version: "2";
      /** Scope */
      scope: string[];
      semantic_support: components["schemas"]["SemanticReview"];
      /** Suggestions */
      suggestions: string[];
      /** Summary */
      summary: string;
      /**
       * Task Type
       * @enum {string}
       */
      task_type: "pr_review" | "ci_debug" | "knowledge_qa";
      /** Unconfirmed */
      unconfirmed: string[];
      /** Verification Steps */
      verification_steps: string[];
    };
    /** Repository */
    Repository: {
      /** Ci Run Count */
      ci_run_count: number;
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /** Default Branch */
      default_branch: string;
      /** Default Commit */
      default_commit: string;
      /** Description */
      description: string;
      /** Document Count */
      document_count: number;
      /** Fetched At */
      fetched_at?: string | null;
      /** Full Name */
      full_name: string;
      /** Id */
      id: string;
      /** Language */
      language: string;
      /** Pull Request Count */
      pull_request_count: number;
      /** Sync Warnings */
      sync_warnings?: components["schemas"]["SourceNotice"][];
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /** RepositoryCreate */
    RepositoryCreate: {
      /** Url */
      url: string;
    };
    /** ReviewDecision */
    ReviewDecision: {
      /**
       * Action
       * @enum {string}
       */
      action: "keep" | "need_evidence" | "downgrade" | "remove";
      /**
       * Category
       * @enum {string}
       */
      category:
        | "none"
        | "citation"
        | "version"
        | "unread"
        | "metadata_conflict"
        | "truncation"
        | "missing_context"
        | "unsupported_cause"
        | "historical_only"
        | "duplicate"
        | "overstated_impact"
        | "unsupported_advice"
        | "calculation"
        | "other";
      /** Evidence */
      evidence: components["schemas"]["Citation"][];
      /** Metadata Evidence */
      metadata_evidence: (
        | "input_version"
        | "resources"
        | "collection_complete"
        | "knowledge_enabled"
        | "current_versions"
        | "reads"
      )[];
      /** Reason */
      reason: string;
      /** Target */
      target: string;
    };
    /** RunBudget */
    RunBudget: {
      /**
       * Max Model Calls
       * @default 6
       */
      max_model_calls: number;
      /**
       * Max Tool Calls
       * @default 12
       */
      max_tool_calls: number;
      /**
       * Max Total Tokens
       * @default 600000
       */
      max_total_tokens: number;
      /**
       * Timeout Seconds
       * @default 600
       */
      timeout_seconds: number;
    };
    /** RunCreate */
    RunCreate: {
      budget?: components["schemas"]["RunBudget"];
      /**
       * Conversation Id
       * Format: uuid
       */
      conversation_id: string;
      /** Question */
      question: string;
      /** Repo Id */
      repo_id: string;
      /** Target Id */
      target_id?: string | null;
      /**
       * Task Type
       * @enum {string}
       */
      task_type: "pr_review" | "ci_debug" | "knowledge_qa";
      /**
       * Use Knowledge
       * @default true
       */
      use_knowledge: boolean;
    };
    /** RunEventResponse */
    RunEventResponse: {
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Event Type */
      event_type: string;
      /** Payload */
      payload: {
        [key: string]: unknown;
      };
      /**
       * Run Id
       * Format: uuid
       */
      run_id: string;
      /** Sequence */
      sequence: number;
    };
    /** RunResponse */
    RunResponse: {
      /** Attempt */
      attempt: number;
      /** Cancel Requested At */
      cancel_requested_at: string | null;
      /** Configuration */
      configuration: {
        [key: string]: unknown;
      };
      /** Configuration Version */
      configuration_version: string;
      /**
       * Conversation Id
       * Format: uuid
       */
      conversation_id: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Error Code */
      error_code:
        | (
            | "model_error"
            | "tool_error"
            | "budget_exceeded"
            | "timeout"
            | "input_changed"
            | "artifact_missing"
            | "worker_lost"
            | "internal_error"
            | "evidence_unavailable"
            | "model_auth_error"
            | "model_balance_error"
            | "model_rate_limited"
            | "model_network_error"
            | "model_format_error"
            | "model_configuration_error"
            | "loop_detected"
            | "cost_budget_exceeded"
            | "pricing_not_configured"
            | "budget_unavailable"
          )
        | null;
      /** Error Message */
      error_message: string | null;
      /**
       * Execution Available
       * @default true
       */
      execution_available: boolean;
      /** Finished At */
      finished_at: string | null;
      /** Heartbeat At */
      heartbeat_at: string | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Input Version */
      input_version: {
        [key: string]: unknown;
      };
      /**
       * Message Id
       * Format: uuid
       */
      message_id: string;
      /** Recovery Count */
      recovery_count: number;
      /** Repo Id */
      repo_id: string;
      /** Result */
      result: {
        [key: string]: unknown;
      } | null;
      /** Retry Of */
      retry_of: string | null;
      /** Started At */
      started_at: string | null;
      /**
       * Status
       * @enum {string}
       */
      status:
        | "queued"
        | "running"
        | "succeeded"
        | "failed"
        | "cancelled"
        | "needs_attention";
      /** Target Id */
      target_id: string | null;
      /**
       * Task Type
       * @enum {string}
       */
      task_type: "pr_review" | "ci_debug" | "knowledge_qa";
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /** RuntimeInfo */
    RuntimeInfo: {
      /**
       * Data Source
       * @enum {string}
       */
      data_source: "fixture" | "github";
      /**
       * Fixture Storage
       * @enum {string}
       */
      fixture_storage: "database" | "files";
      /**
       * Github Configured
       * @default false
       */
      github_configured: boolean;
      model: components["schemas"]["ModelInfo"];
      /** Repository Adapter Available */
      repository_adapter_available: boolean;
      /** Task Execution Available */
      task_execution_available: boolean;
    };
    /** SemanticReview */
    SemanticReview: {
      /** Notes */
      notes?: string[];
      /** Reviewer */
      reviewer?: string | null;
      /**
       * Status
       * @default not_reviewed
       * @enum {string}
       */
      status: "not_reviewed" | "supported" | "partial" | "unsupported";
    };
    /** SourceNotice */
    SourceNotice: {
      /** Code */
      code: string;
      /** Message */
      message: string;
      /** Retry After */
      retry_after?: number | null;
    };
    /** ValidationError */
    ValidationError: {
      /** Context */
      ctx?: Record<string, never>;
      /** Input */
      input?: unknown;
      /** Location */
      loc: (string | number)[];
      /** Message */
      msg: string;
      /** Error Type */
      type: string;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  artifact_api_v1_artifacts__artifact_id__get: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        artifact_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ArtifactContent"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  summary_api_v1_budget_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["BudgetResponse"];
        };
      };
    };
  };
  conversations_api_v1_conversations_get: {
    parameters: {
      query: {
        repo_id: string;
        limit?: number;
        offset?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_ConversationResponse_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  post_conversation_api_v1_conversations_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ConversationCreate"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ConversationResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  conversation_api_v1_conversations__conversation_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        conversation_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ConversationResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  messages_api_v1_conversations__conversation_id__messages_get: {
    parameters: {
      query?: {
        limit?: number;
        offset?: number;
      };
      header?: never;
      path: {
        conversation_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_MessageResponse_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  post_message_api_v1_conversations__conversation_id__messages_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        conversation_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["MessageCreate"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MessageResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  health_api_v1_health_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HealthResponse"];
        };
      };
      /** @description Dependencies are not ready */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HealthResponse"];
        };
      };
    };
  };
  liveness_api_v1_health_live_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": {
            [key: string]: string;
          };
        };
      };
    };
  };
  documents_api_v1_knowledge_get: {
    parameters: {
      query: {
        repo_id: string;
        limit?: number;
        offset?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_KnowledgeDocumentOutput_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  search_api_v1_knowledge_search_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["KnowledgeSearch"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["KnowledgeSearchOutput"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  status_api_v1_knowledge_status_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": unknown;
        };
      };
    };
  };
  upload_api_v1_knowledge_upload_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["KnowledgeUpload"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["KnowledgeUploadOutput"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  detail_api_v1_knowledge__document_id__get: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        document_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["KnowledgeDetail"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  remove_api_v1_knowledge__document_id__delete_post: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        document_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  preview_api_v1_knowledge__document_id__versions__version_id__get: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        document_id: string;
        version_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["KnowledgePreview"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  memories_api_v1_memories_get: {
    parameters: {
      query: {
        repo_id: string;
        limit?: number;
        offset?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_MemoryOutput_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  search_api_v1_memories_search_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["MemorySearch"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  approve_api_v1_memories__memory_id__approve_post: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        memory_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["MemoryApprove"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MemoryOutput"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  edit_api_v1_memories__memory_id__edit_post: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        memory_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["MemoryEdit"];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MemoryOutput"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  reindex_api_v1_memories__memory_id__index_post: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        memory_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MemoryOutput"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  revoke_api_v1_memories__memory_id__revoke_post: {
    parameters: {
      query: {
        repo_id: string;
      };
      header?: never;
      path: {
        memory_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MemoryOutput"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  repositories_api_v1_repositories_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Collection_Repository_"];
        };
      };
    };
  };
  add_repository_api_v1_repositories_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["RepositoryCreate"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Repository"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  repository_api_v1_repositories__repo_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Repository"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  ci_runs_api_v1_repositories__repo_id__ci_runs_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Collection_CIRunSummary_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  ci_run_api_v1_repositories__repo_id__ci_runs__run_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
        run_id: number;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["CIRunDetail"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  job_logs_api_v1_repositories__repo_id__ci_runs__run_id__jobs__job_id__logs_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
        run_id: number;
        job_id: number;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["JobLog"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  documents_api_v1_repositories__repo_id__documents_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Collection_DocumentSummary_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  document_api_v1_repositories__repo_id__documents__document_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
        document_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DocumentDetail"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  pull_requests_api_v1_repositories__repo_id__pull_requests_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Collection_PullRequestSummary_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  pull_request_api_v1_repositories__repo_id__pull_requests__number__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
        number: number;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PullRequestDetail"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  refresh_repository_api_v1_repositories__repo_id__refresh_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        repo_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Repository"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  runs_api_v1_runs_get: {
    parameters: {
      query: {
        repo_id: string;
        conversation_id?: string | null;
        limit?: number;
        offset?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_RunResponse_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  post_run_api_v1_runs_post: {
    parameters: {
      query?: never;
      header?: {
        "idempotency-key"?: string | null;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["RunCreate"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RunResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  run_api_v1_runs__run_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RunResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  artifacts_api_v1_runs__run_id__artifacts_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_ArtifactResponse_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  post_cancel_api_v1_runs__run_id__cancel_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RunResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  context_history_api_v1_runs__run_id__context_get: {
    parameters: {
      query?: {
        call?: number | null;
      };
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ContextResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  run_cost_api_v1_runs__run_id__cost_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["CostResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  events_api_v1_runs__run_id__events_get: {
    parameters: {
      query?: {
        after?: number;
        limit?: number;
      };
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EventPage"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  evidence_api_v1_runs__run_id__evidence_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_EvidenceResponse_"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  freshness_api_v1_runs__run_id__freshness_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["FreshnessResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  extract_api_v1_runs__run_id__memories_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["MemoryExtract"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MemoryOutput"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  revoke_source_api_v1_runs__run_id__memories_revoke_source_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  report_api_v1_runs__run_id__report_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ReportResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  post_retry_api_v1_runs__run_id__retry_post: {
    parameters: {
      query?: never;
      header: {
        "idempotency-key": string;
      };
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RunResponse"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  run_stream_api_v1_runs__run_id__stream_get: {
    parameters: {
      query?: {
        after?: number;
      };
      header?: {
        "last-event-id"?: string | null;
      };
      path: {
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "text/event-stream": string;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  runtime_api_v1_runtime_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RuntimeInfo"];
        };
      };
    };
  };
}
