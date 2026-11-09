import { useState } from "react";
import type { JsonValue } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import type { LocalProjectApi } from "../../../api/local-client";
import { RuntimeOutputView } from "../../runtime/RuntimeOutputView";

export function AgentInputReply({ question, context, locale, busy, projectId, api, onReply, onStop }: {
  question: string; context?: JsonValue; locale: "zh" | "en"; busy: boolean;
  projectId: string; api: LocalProjectApi; onReply: (reply: string) => Promise<void>;
  onStop: () => void;
}) {
  const [reply, setReply] = useState("");
  const zh = locale === "zh";
  return <form className="agent-app-approval" aria-label={zh ? "补充任务信息" : "Provide task information"}
    onSubmit={(event) => { event.preventDefault(); if (reply.trim() && !busy) void onReply(reply); }}>
    <p className="agent-app-input-question" aria-live="polite">{question}</p>
    {context != null ? <details>
      <summary>{zh ? "查看本轮方案与补充信息" : "View this turn’s options and context"}</summary>
      <RuntimeOutputView result={context} locale={locale} projectId={projectId} api={api} />
    </details> : null}
    <label className="field"><span>{zh ? "你的回答" : "Your reply"}</span>
      <textarea name="reply" autoComplete="off" maxLength={8000} rows={3} value={reply} disabled={busy}
        placeholder={zh ? "补充信息或选择方案…" : "Add information or choose an option…"}
        onChange={(event) => setReply(event.target.value)} /></label>
    <div className="agent-app-approval-actions">
      <Button type="submit" variant="primary" disabled={!reply.trim() || busy}>{busy ? (zh ? "正在提交…" : "Submitting…") : (zh ? "提交并继续" : "Submit and continue")}</Button>
      <Button type="button" variant="ghost" disabled={busy} onClick={onStop}>{zh ? "取消任务" : "Cancel task"}</Button>
    </div>
  </form>;
}
