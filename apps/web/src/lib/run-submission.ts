// 文件用途：合并重复点击，并在请求结果未知时保留相同任务参数与幂等键。
import type { Run, RunCreate } from "./workflows";

export class RunSubmission {
  private intent?: { fingerprint: string; key: string };
  private active?: Promise<Run>;
  submit(
    data: RunCreate,
    send: (data: RunCreate, key: string) => Promise<Run>,
  ): Promise<Run> {
    // 请求进行中直接复用 Promise，防止 React 重绘之前发生第二次提交。
    if (this.active) return this.active;
    const fingerprint = JSON.stringify(data);
    if (this.intent?.fingerprint !== fingerprint)
      this.intent = { fingerprint, key: crypto.randomUUID() };
    const key = this.intent.key;
    this.active = Promise.resolve()
      .then(() => send(data, key))
      .finally(() => {
        this.active = undefined;
      });
    return this.active;
  }
}
