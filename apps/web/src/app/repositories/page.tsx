// 文件用途：兼容原仓库列表地址，统一返回仓库概览首页。
import { redirect } from "next/navigation";

export default function RepositoriesPage() {
  redirect("/");
}
