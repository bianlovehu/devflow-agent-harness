// 文件用途：提供开发环境专用的可拖动工具入口和中文偏好设置，不修改 Next.js 内部代码。
"use client";
import { useEffect, useRef, useState } from "react";
import { clampDevPosition } from "@/lib/dev-tool-position";
import "./dev-tools.css";

type Preferences = {
  x: number;
  y: number;
  theme: "system" | "light" | "dark";
  size: "small" | "medium" | "large";
};
const defaults: Preferences = { x: 20, y: 20, theme: "system", size: "medium" };
const sizes = { small: 36, medium: 44, large: 54 };
const storageKey = "devflow.dev-tools.preferences.v1";
const hideKey = "devflow.dev-tools.hidden";
export function DevTools() {
  const [preferences, setPreferences] = useState(defaults);
  const [ready, setReady] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [open, setOpen] = useState(false);
  const drag = useRef<{
    x: number;
    y: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      let saved = defaults;
      try {
        const value = JSON.parse(localStorage.getItem(storageKey) ?? "null");
        if (
          value &&
          ["system", "light", "dark"].includes(value.theme) &&
          ["small", "medium", "large"].includes(value.size)
        )
          saved = value;
        setHidden(sessionStorage.getItem(hideKey) === "1");
      } catch {
        /* 存储不可用时仍可拖动和使用设置。 */
      }
      const size = sizes[saved.size];
      const position = clampDevPosition(
        saved === defaults ? 20 : saved.x,
        saved === defaults ? window.innerHeight - size - 20 : saved.y,
        window.innerWidth,
        window.innerHeight,
        size,
      );
      setPreferences({ ...saved, ...position });
      setReady(true);
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(preferences));
    } catch {
      /* 无持久化权限时保留本页状态。 */
    }
  }, [preferences, ready]);
  useEffect(() => {
    function resize() {
      setPreferences((value) => ({
        ...value,
        ...clampDevPosition(
          value.x,
          value.y,
          window.innerWidth,
          window.innerHeight,
          sizes[value.size],
        ),
      }));
    }
    function keydown(event: KeyboardEvent) {
      if (event.altKey && event.shiftKey && event.code === "KeyN") {
        event.preventDefault();
        setHidden(false);
        setOpen((value) => !value);
        try {
          sessionStorage.removeItem(hideKey);
        } catch {
          /* 仅影响恢复记忆。 */
        }
      }
      if (event.key === "Escape" && open) {
        setOpen(false);
        button.current?.focus();
      }
    }
    window.addEventListener("resize", resize);
    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("resize", resize);
      window.removeEventListener("keydown", keydown);
    };
  }, [open]);
  useEffect(() => {
    if (open) panel.current?.focus();
  }, [open]);
  if (!ready || hidden) return null;
  const size = sizes[preferences.size];
  const dark = preferences.theme === "dark";
  return (
    <aside className="devflow-dev-tools" data-theme={preferences.theme}>
      <button
        ref={button}
        type="button"
        className="devflow-dev-orb"
        aria-label="开发工具：点击打开设置，拖动调整位置"
        aria-expanded={open}
        aria-controls="devflow-dev-preferences"
        style={{
          left: preferences.x,
          top: preferences.y,
          width: size,
          height: size,
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          drag.current = {
            x: preferences.x,
            y: preferences.y,
            startX: event.clientX,
            startY: event.clientY,
            moved: false,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const value = drag.current;
          if (!value || !event.currentTarget.hasPointerCapture(event.pointerId))
            return;
          const dx = event.clientX - value.startX,
            dy = event.clientY - value.startY;
          if (Math.hypot(dx, dy) > 4) value.moved = true;
          if (value.moved)
            setPreferences((current) => ({
              ...current,
              ...clampDevPosition(
                value.x + dx,
                value.y + dy,
                window.innerWidth,
                window.innerHeight,
                size,
              ),
            }));
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => {
          if (drag.current) drag.current.moved = true;
        }}
        onClick={(event) => {
          if (event.detail === 0 || !drag.current?.moved)
            setOpen((value) => !value);
        }}
      >
        N
      </button>
      {open && (
        <div
          ref={panel}
          id="devflow-dev-preferences"
          role="dialog"
          aria-label="开发工具偏好设置"
          tabIndex={-1}
          className="devflow-dev-panel"
          data-dark={dark || undefined}
          style={{
            maxHeight: Math.max(
              80,
              preferences.y > window.innerHeight / 2
                ? preferences.y - 16
                : window.innerHeight - preferences.y - size - 24,
            ),
            left: Math.min(
              Math.max(8, preferences.x),
              Math.max(8, window.innerWidth - 368),
            ),
            top:
              preferences.y > window.innerHeight / 2
                ? undefined
                : preferences.y + size + 8,
            bottom:
              preferences.y > window.innerHeight / 2
                ? window.innerHeight - preferences.y + 8
                : undefined,
          }}
        >
          <header>
            <strong>偏好设置</strong>
            <button
              type="button"
              aria-label="关闭偏好设置"
              onClick={() => {
                setOpen(false);
                button.current?.focus();
              }}
            >
              ×
            </button>
          </header>
          <label>
            <span>
              <strong>主题</strong>
              <small>设置开发工具面板的显示主题。</small>
            </span>
            <select
              value={preferences.theme}
              onChange={(event) =>
                setPreferences((value) => ({
                  ...value,
                  theme: event.target.value as Preferences["theme"],
                }))
              }
            >
              <option value="system">跟随系统</option>
              <option value="light">浅色</option>
              <option value="dark">深色</option>
            </select>
          </label>
          <section>
            <strong>位置</strong>
            <p>按住 N 小球即可自由拖动，位置会自动保存。</p>
            <button
              type="button"
              onClick={() =>
                setPreferences((value) => ({
                  ...value,
                  x: 20,
                  y: Math.max(8, window.innerHeight - sizes[value.size] - 20),
                }))
              }
            >
              恢复左下角
            </button>
          </section>
          <label>
            <span>
              <strong>大小</strong>
              <small>调整开发工具入口的大小。</small>
            </span>
            <select
              value={preferences.size}
              onChange={(event) => {
                const next = event.target.value as Preferences["size"];
                setPreferences((value) => ({
                  ...value,
                  size: next,
                  ...clampDevPosition(
                    value.x,
                    value.y,
                    window.innerWidth,
                    window.innerHeight,
                    sizes[next],
                  ),
                }));
              }}
            >
              <option value="small">小</option>
              <option value="medium">中</option>
              <option value="large">大</option>
            </select>
          </label>
          <section>
            <strong>本次会话隐藏</strong>
            <p>使用 Alt + Shift + N 可重新显示开发工具。</p>
            <button
              type="button"
              onClick={() => {
                try {
                  sessionStorage.setItem(hideKey, "1");
                } catch {
                  /* 本页仍可隐藏。 */
                }
                setHidden(true);
                setOpen(false);
              }}
            >
              隐藏开发工具
            </button>
          </section>
          <footer>
            DevFlow 开发辅助面板 · 仅在开发环境显示。
            <br />
            Next.js 编译及运行错误仍会正常提示。
          </footer>
        </div>
      )}
    </aside>
  );
}
