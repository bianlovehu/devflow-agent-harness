// 文件用途：将白名单内的只读业务请求转发到后端。
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function allowedPath(path: string[]): boolean {
  if (path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part))) return false;
  if (path.length === 1 && path[0] === "runtime") return true;
  if (path[0] !== "repositories" || path.length > 4) return false;
  if (path.length <= 2) return true;
  if (!["pull-requests", "ci-runs", "documents"].includes(path[2]))
    return false;
  return path.length === 3 || path[2] === "documents" || /^\d+$/.test(path[3]);
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  // 先校验路径白名单，避免把这个代理变成任意接口或任意地址的转发入口。
  if (!allowedPath(path)) {
    return NextResponse.json(
      { detail: { code: "not_found", message: "资源路径不存在" } },
      { status: 404 },
    );
  }
  try {
    const base = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    const url = new URL(
      `/api/v1/${path.map(encodeURIComponent).join("/")}`,
      base,
    );
    // 只转发到服务端配置的后端地址，不复制浏览器提交的鉴权头。
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    const body = await response.json();
    return NextResponse.json(body, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        detail: {
          code: "backend_unavailable",
          message: "后端未连接，请启动 API 后重试",
        },
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
