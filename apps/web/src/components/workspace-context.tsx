// 文件用途：共享当前仓库及会话上下文，保留跨页选择并以直达地址为准。
"use client";
import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
} from "react";
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  fetchData,
  type Collection,
  type Repository,
  type RuntimeInfo,
} from "@/lib/repositories";
import type { Run } from "@/lib/workflows";

const storageKey = "devflow.repository";
function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener("devflow-repository", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("devflow-repository", listener);
  };
}
function snapshot() {
  try {
    return localStorage.getItem(storageKey) ?? "";
  } catch {
    return "";
  }
}
function remember(id: string) {
  try {
    localStorage.setItem(storageKey, id);
  } catch {
    /* 私密浏览仍可通过 URL 选择仓库。 */
  }
  window.dispatchEvent(new Event("devflow-repository"));
}
function useWorkspaceState() {
  const params = useParams<{ repoId?: string; runId?: string }>();
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const stored = useSyncExternalStore(subscribe, snapshot, () => "");
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: ({ signal }) =>
      fetchData<Collection<Repository>>("repositories", { signal }),
  });
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: () => fetchData<RuntimeInfo>("runtime"),
    staleTime: 30000,
  });
  const run = useQuery<Run>({
    queryKey: ["run", params.runId],
    queryFn: ({ signal }) => fetchData<Run>(`runs/${params.runId}`, { signal }),
    enabled: Boolean(params.runId),
  });
  const queryRepo = search.get("repo");
  const validQueryRepo =
    queryRepo && /^[a-zA-Z0-9_-]{1,80}$/.test(queryRepo)
      ? queryRepo
      : undefined;
  const explicit =
    params.repoId || (params.runId ? run.data?.repo_id : validQueryRepo);
  const repoId =
    explicit ||
    (repositories.data?.items.some((r) => r.id === stored)
      ? stored
      : repositories.data?.items[0]?.id);
  const repository = repositories.data?.items.find((r) => r.id === repoId);
  const queryConversation = search.get("conversation");
  const conversationId = params.runId
    ? run.data?.conversation_id
    : queryConversation && /^[0-9a-f-]{36}$/i.test(queryConversation)
      ? queryConversation
      : undefined;
  const available =
    runtime.data?.data_source === "github" ||
    runtime.data?.fixture_storage === "database";
  useEffect(() => {
    if (explicit) remember(explicit);
  }, [explicit]);
  function href(path: string) {
    return repoId ? `${path}?repo=${encodeURIComponent(repoId)}` : path;
  }
  function chooseRepository(id: string) {
    remember(id);
    const path = pathname.startsWith("/knowledge")
      ? "/knowledge"
      : pathname.startsWith("/memories")
        ? "/memories"
        : "/runs";
    router.push(
      pathname.startsWith("/repositories")
        ? `/repositories/${encodeURIComponent(id)}`
        : `${path}?repo=${encodeURIComponent(id)}`,
    );
  }
  return {
    repoId,
    repository,
    repositories,
    runtime,
    conversationId,
    available,
    href,
    chooseRepository,
  };
}
const WorkspaceContext = createContext<ReturnType<
  typeof useWorkspaceState
> | null>(null);
export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const value = useWorkspaceState();
  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}
export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("工作空间上下文未就绪");
  return value;
}
