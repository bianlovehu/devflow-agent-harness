// 文件用途：设置页面元数据，并挂载共享导航和查询状态。
import type { Metadata } from "next";
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
          <WorkspaceShell>{children}</WorkspaceShell>
        </Providers>
      </body>
    </html>
  );
}
