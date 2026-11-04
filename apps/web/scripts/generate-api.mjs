// 文件用途：从后端 OpenAPI 生成前端类型，并检查已提交类型是否过期。
import { spawnSync } from "node:child_process";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import openapiTS, { astToString } from "openapi-typescript";
import prettier from "prettier";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const python =
  process.env.DEVFLOW_PYTHON ??
  path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
// 直接读取应用 schema，不读取在线服务，避免环境状态和密钥参与生成。
const result = spawnSync(
  python,
  [path.join(root, "scripts/export_openapi.py")],
  { cwd: root, encoding: "utf8", maxBuffer: 8 * 1024 * 1024 },
);
if (result.error || result.status !== 0)
  throw new Error("OpenAPI 导出失败，请先初始化 Python 依赖。", {
    cause: result.error ?? result.stderr,
  });
const ast = await openapiTS(JSON.parse(result.stdout));
const generated = await prettier.format(
  "// 文件用途：保存从 FastAPI OpenAPI 自动生成的接口类型，请勿手工修改。\n" +
    astToString(ast),
  { parser: "typescript", endOfLine: "crlf" },
);
const target = path.join(root, "apps/web/src/lib/generated/api.d.ts");
if (process.argv.includes("--check")) {
  if ((await readFile(target, "utf8").catch(() => "")) !== generated)
    throw new Error("前端接口类型已过期，请运行 npm run api:generate。");
  console.log("OpenAPI 类型与后端一致。");
} else {
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, generated);
  console.log("已生成 src/lib/generated/api.d.ts");
}
