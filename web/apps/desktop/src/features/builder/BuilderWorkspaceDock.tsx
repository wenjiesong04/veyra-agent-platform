import * as React from "react";
import { Maximize2, Minimize2, X } from "lucide-react";
import { IconButton, useTheme } from "@veyra/ui";

type Locale = "zh" | "en";
export type BuilderWorkspaceTab = "workbench" | "test";

const copy = {
  zh: {
    workbench: "工作台",
    test: "测试",
    close: "关闭工作台",
    expand: "全屏",
    collapse: "退出全屏",
    testEmpty: "Agent 创建并通过结构验证后，在这里显式测试运行。",
  },
  en: {
    workbench: "Workbench",
    test: "Test",
    close: "Close workbench",
    expand: "Full screen",
    collapse: "Exit full screen",
    testEmpty: "After the Agent is created and validated, start an explicit test run here.",
  },
} as const;

type Particle = { x: number; y: number; vx: number; vy: number; r: number; a: number };

function readAccent(node: HTMLElement): { fill: string; line: string } {
  const styles = getComputedStyle(node);
  const accent = styles.getPropertyValue("--accent-strong").trim() || styles.getPropertyValue("--accent").trim();
  return {
    fill: accent || "rgba(92, 124, 250, 0.9)",
    line: accent || "rgba(92, 124, 250, 0.45)",
  };
}

function BuilderLiveField({ live }: { live: boolean }) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const { reducedMotion } = useTheme();
  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const animated = live && !reducedMotion;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext("2d");
    } catch {
      return;
    }
    if (!ctx) return;
    const host = canvas.parentElement ?? canvas;
    const colors = readAccent(host);
    let frame = 0;
    let width = 0;
    let height = 0;
    const particles: Particle[] = [];
    const resize = () => {
      const nextWidth = host.clientWidth || 1;
      const nextHeight = host.clientHeight || 1;
      const ratio = window.devicePixelRatio || 1;
      width = nextWidth;
      height = nextHeight;
      canvas.width = Math.round(nextWidth * ratio);
      canvas.height = Math.round(nextHeight * ratio);
      canvas.style.width = `${nextWidth}px`;
      canvas.style.height = `${nextHeight}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      if (!particles.length) {
        const count = Math.max(20, Math.min(56, Math.round((nextWidth * nextHeight) / 16000)));
        for (let index = 0; index < count; index += 1) {
          particles.push({
            x: Math.random() * nextWidth,
            y: Math.random() * nextHeight,
            vx: (Math.random() - 0.5) * 0.32,
            vy: (Math.random() - 0.5) * 0.32,
            r: 0.7 + Math.random() * 1.8,
            a: 0.16 + Math.random() * 0.38,
          });
        }
      }
    };
    resize();
    const draw = () => {
      const speed = live ? 1 : 0.42;
      const link = live ? 108 : 84;
      ctx.clearRect(0, 0, width, height);
      for (const particle of particles) {
        if (animated) {
          particle.x += particle.vx * speed;
          particle.y += particle.vy * speed;
          if (particle.x < -8) particle.x = width + 8;
          if (particle.x > width + 8) particle.x = -8;
          if (particle.y < -8) particle.y = height + 8;
          if (particle.y > height + 8) particle.y = -8;
        }
        ctx.beginPath();
        ctx.globalAlpha = particle.a * (live ? 1 : 0.55);
        ctx.fillStyle = colors.fill;
        ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = live ? 0.2 : 0.1;
      ctx.strokeStyle = colors.line;
      ctx.lineWidth = 1;
      for (let i = 0; i < particles.length; i += 1) {
        for (let j = i + 1; j < particles.length; j += 1) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.hypot(dx, dy);
          if (dist > link) continue;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;
      if (animated) frame = window.requestAnimationFrame(draw);
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      resize();
      if (!animated) draw();
    });
    observer?.observe(host);
    draw();
    return () => {
      observer?.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [live, reducedMotion]);
  return <canvas ref={canvasRef} className="builder-live-field" aria-hidden="true" />;
}

export function BuilderWorkspaceDock({
  locale,
  live,
  tab,
  onTabChange,
  expanded,
  onToggleExpand,
  onClose,
  workbench,
  test,
  idPrefix = "builder",
}: {
  locale: Locale;
  live: boolean;
  tab: BuilderWorkspaceTab;
  onTabChange: (tab: BuilderWorkspaceTab) => void;
  expanded: boolean;
  onToggleExpand: () => void;
  onClose: () => void;
  workbench: React.ReactNode;
  test: React.ReactNode;
  idPrefix?: string;
}) {
  const text = copy[locale];
  const [testReady, setTestReady] = React.useState(tab === "test");
  React.useEffect(() => {
    if (tab === "test") setTestReady(true);
  }, [tab]);
  const workbenchTabId = `${idPrefix}-tab-workbench`;
  const testTabId = `${idPrefix}-tab-test`;
  const workbenchPanelId = `${idPrefix}-panel-workbench`;
  const testPanelId = `${idPrefix}-panel-test`;
  return (
    <aside className={`builder-workspace-dock${live ? " is-live" : ""}${expanded ? " is-expanded" : ""}`} aria-label={text.workbench}>
      <header className="builder-workspace-head">
        <div className="builder-workspace-tabs" role="tablist" aria-label={text.workbench}>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "workbench"}
            id={workbenchTabId}
            aria-controls={workbenchPanelId}
            className="builder-workspace-tab"
            onClick={() => onTabChange("workbench")}
          >
            {text.workbench}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "test"}
            id={testTabId}
            aria-controls={testPanelId}
            className="builder-workspace-tab"
            onClick={() => onTabChange("test")}
          >
            {text.test}
          </button>
        </div>
        <div className="builder-workspace-head-actions">
          <IconButton icon={expanded ? Minimize2 : Maximize2} label={expanded ? text.collapse : text.expand} onClick={onToggleExpand} />
          <IconButton icon={X} label={text.close} onClick={onClose} />
        </div>
      </header>
      <div className="builder-workspace-stage">
        <BuilderLiveField live={live} />
        <div
          className="builder-workspace-panel"
          role="tabpanel"
          id={workbenchPanelId}
          aria-labelledby={workbenchTabId}
          hidden={tab !== "workbench"}
        >
          {workbench}
        </div>
        <div
          className="builder-workspace-panel"
          role="tabpanel"
          id={testPanelId}
          aria-labelledby={testTabId}
          hidden={tab !== "test"}
        >
          {testReady ? test ?? <p className="factory-canvas-kicker">{text.testEmpty}</p> : null}
        </div>
      </div>
    </aside>
  );
}
