// 文件用途：将受限的业务读取与任务创建请求交给统一后端代理。
import { forwardBackend } from "@/lib/backend-proxy";

export const dynamic = "force-dynamic";

async function handle(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  return forwardBackend(request, path);
}

export { handle as GET, handle as POST };
