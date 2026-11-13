// 文件用途：设置页面元数据，并挂载共享导航和查询状态。
import type { Metadata } from "next";
import { Suspense } from "react";
import { DevTools } from "@/components/dev-tools";
import { Providers } from "@/components/providers";
import { WorkspaceShell } from "@/components/workspace-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevFlow · 研发协作工作台",
  description: "有证据、可追溯的 PR 审查与 CI 排障",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>
          <Suspense
            fallback={<div className="app-loading">正在打开工作空间…</div>}
          >
            <WorkspaceShell>{children}</WorkspaceShell>
          </Suspense>
        </Providers>
        {process.env.NODE_ENV === "development" && <DevTools />}
      </body>
    </html>
  );
}
