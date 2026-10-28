// 文件用途：代理后端健康检查，并返回明确的不可用状态。
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const base = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(new URL("/api/v1/health", base), {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (response.status !== 200 && response.status !== 503) {
      throw new Error("Unexpected backend response");
    }
    return NextResponse.json(await response.json(), {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        status: "unavailable",
        service: "devflow-api",
        version: "unknown",
        checked_at: new Date().toISOString(),
        checks: {
          api: {
            status: "error",
            message: "后端未连接，请启动 API 服务",
            version: null,
          },
        },
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
