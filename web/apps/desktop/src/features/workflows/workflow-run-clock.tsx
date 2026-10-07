import { useEffect, useState } from "react";

export function WorkflowRunClock({ startedAt, finishedAt, active, locale }: {
  startedAt: string; finishedAt: string | null; active: boolean; locale: "zh" | "en";
}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const started = Date.parse(startedAt);
  const end = finishedAt ? Date.parse(finishedAt) : now;
  if (!Number.isFinite(started) || !Number.isFinite(end)) return null;
  const seconds = Math.max(0, Math.floor((end - started) / 1000));
  const duration = seconds < 60 ? `${seconds}${locale === "zh" ? " 秒" : "s"}` : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return <span className="workflow-run-clock" aria-label={locale === "zh" ? "运行用时" : "Run elapsed time"}>{locale === "zh" ? "用时" : "Elapsed"} {duration}</span>;
}
