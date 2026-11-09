import { ArrowUpRight, ChevronDown, History, X } from "lucide-react";
import { IconButton, LinkButton, StatusBadge } from "@veyra/ui";
import { projectRoutePaths, type AgentConversationSummary, type AgentRunResponse, type ArtifactRef } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../../api/local-client";
import { relativeActivityTime } from "../agent-navigation";
import { displayConversationTitle } from "../conversation-title";
import { runStatusLabel, runTone } from "../../studio/studio-run-ui";
import { ArtifactCard } from "../../runtime/RuntimeInputForm";
import "./agent-app-context.css";

type Locale = "zh" | "en";

export function AgentAppContextPanel({
  locale, projectId, agentId, description, version, run, files, history,
  conversations, conversationId, onConversation, onClose, api,
}: {
  locale: Locale;
  projectId: string;
  agentId: string;
  description: string;
  version: number | null;
  run: AgentRunResponse | null;
  files: ArtifactRef[];
  history: AgentRunResponse[];
  conversations: AgentConversationSummary[];
  conversationId: string | null;
  onConversation: (id: string) => void;
  onClose: () => void;
  api: LocalProjectApi;
}) {
  const zh = locale === "zh";
  const [narrow, setNarrow] = useState(() => window.matchMedia?.("(max-width: 1100px)").matches ?? false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const query = window.matchMedia?.("(max-width: 1100px)");
    if (!query) return;
    const sync = () => setNarrow(query.matches);
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    if (!narrow) return;
    const dialog = dialogRef.current;
    const previous = document.activeElement;
    dialog?.showModal?.();
    return () => {
      dialog?.close?.();
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [narrow]);
  const uniqueFiles = files.filter((file, index, all) => all.findIndex((item) => item.artifact_id === file.artifact_id) === index);
  const contents = <>
    <header><h2>{zh ? "任务上下文" : "Task context"}</h2><IconButton icon={X} label={zh ? "关闭上下文" : "Close context"} title={zh ? "关闭上下文" : "Close context"} onClick={onClose} /></header>
    <div className="agent-app-context-scroll">
      <section>
        <h3>Agent</h3>
        <dl><div><dt>{zh ? "固定版本" : "Pinned version"}</dt><dd>{version ? `v${version}` : "-"}</dd></div></dl>
        {description ? <details className="agent-app-description">
          <summary><span>{zh ? "任务说明" : "Task brief"}</span><ChevronDown size={14} aria-hidden="true" /></summary>
          <p>{description}</p>
        </details> : null}
      </section>
      {run ? <section>
        <h3>{zh ? "本次运行" : "Current run"}</h3>
        <div className="agent-app-context-run"><StatusBadge label={runStatusLabel(run.status, locale)} tone={runTone(run.status)} /><time dateTime={run.created_at}>{relativeActivityTime(run.created_at, locale)}</time></div>
        <LinkButton icon={ArrowUpRight} variant="ghost" size="sm" href={`${projectRoutePaths.agentRun(projectId, agentId)}?run_id=${encodeURIComponent(run.run_id)}`}>{zh ? "查看运行详情" : "Run details"}</LinkButton>
      </section> : null}
      {uniqueFiles.length ? <section>
        <h3>{zh ? "输入材料" : "Task files"}<span>{uniqueFiles.length}</span></h3>
        <ul className="agent-app-context-files">{uniqueFiles.map((file) => <li key={file.artifact_id}><ArtifactCard item={file} locale={locale} projectId={projectId} api={api} compact /></li>)}</ul>
      </section> : null}
      {conversations.length ? <section>
        <h3>{zh ? "对话" : "Conversations"}</h3>
        <ul className="agent-app-context-conversations">{conversations.map((conversation) => <li key={conversation.conversation_id}>
          <button type="button" aria-label={displayConversationTitle(conversation.title, locale)} aria-current={conversation.conversation_id === conversationId ? "true" : undefined} onClick={() => onConversation(conversation.conversation_id)}>
            <span>{displayConversationTitle(conversation.title, locale)}</span>
            <small aria-hidden="true">{relativeActivityTime(conversation.updated_at, locale)}</small>
          </button>
        </li>)}</ul>
      </section> : null}
      <section>
        <h3><History size={15} aria-hidden="true" />{zh ? "最近运行" : "Recent runs"}</h3>
        {history.length ? <ol className="agent-app-context-history">{history.map((item) => <li key={item.run_id}>
          <a href={`${projectRoutePaths.agentRun(projectId, agentId)}?run_id=${encodeURIComponent(item.run_id)}`} aria-label={`${runStatusLabel(item.status, locale)} ${relativeActivityTime(item.created_at, locale)}`}>
            <time dateTime={item.created_at}>{relativeActivityTime(item.created_at, locale)}</time>
            <StatusBadge label={runStatusLabel(item.status, locale)} tone={runTone(item.status)} />
          </a>
        </li>)}</ol> : <p className="agent-app-context-empty">{zh ? "暂无运行记录" : "No runs yet"}</p>}
      </section>
    </div>
  </>;
  return narrow ? <dialog ref={dialogRef} className="agent-app-context" aria-label={zh ? "任务上下文" : "Task context"} onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>{contents}</dialog>
    : <aside className="agent-app-context" aria-label={zh ? "任务上下文" : "Task context"}>{contents}</aside>;
}
import { useEffect, useRef, useState } from "react";
