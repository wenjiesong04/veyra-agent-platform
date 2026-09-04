import * as React from "react";
import { Bot, Check, FolderKanban, Plus, Search } from "lucide-react";
import type { ProjectAgentRecord, ProjectSummaryResponse } from "@veyra/api-contracts";
import { folderLabel, sameChatTarget, type ChatTarget } from "./chat-scope";

type Locale = "zh" | "en";

const copy = {
  zh: {
    pick: "选择项目",
    search: "搜索项目",
    create: "新建项目",
    empty: "没有匹配的项目",
    createFailed: "无法创建项目。",
  },
  en: {
    pick: "Choose project",
    search: "Search projects",
    create: "New project",
    empty: "No matching projects",
    createFailed: "The Project could not be created.",
  },
} as const;

function triggerLabel(current: ChatTarget, locale: Locale): string {
  if (current.kind === "agent") return current.name;
  if (current.kind === "project") return current.name;
  return copy[locale].pick;
}

export function ConversationScopePicker({
  locale,
  current,
  projects,
  onSelect,
  onCreateProject,
}: {
  locale: Locale;
  current: ChatTarget;
  projects: ProjectSummaryResponse[];
  onSelect: (target: ChatTarget) => void | Promise<void>;
  onCreateProject: () => void | Promise<void>;
}) {
  const text = copy[locale];
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [hint, setHint] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const searchRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    searchRef.current?.focus();
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  React.useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const run = async (action: () => void | Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setHint("");
    try {
      await action();
      setOpen(false);
    } catch {
      setHint(text.createFailed);
    } finally {
      setBusy(false);
    }
  };

  const choose = (target: ChatTarget) => {
    if (sameChatTarget(current, target)) {
      setOpen(false);
      return;
    }
    void run(() => onSelect(target));
  };

  const needle = query.trim().toLowerCase();
  const visible = projects.filter((project) => {
    if (!needle) return true;
    if (project.name.toLowerCase().includes(needle)) return true;
    if (folderLabel(project.root_path).toLowerCase().includes(needle)) return true;
    return project.agents.some((agent) => (agent.name || agent.slug).toLowerCase().includes(needle));
  });

  return (
    <div className="agent-convo-context">
      <div className="agent-convo-scope" ref={rootRef}>
        <button
          className="agent-convo-context-chip agent-convo-scope-trigger"
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={text.pick}
          disabled={busy}
          onClick={() => setOpen((value) => !value)}
        >
          {current.kind === "agent" ? <Bot size={14} aria-hidden="true" /> : <FolderKanban size={14} aria-hidden="true" />}
          <span>{triggerLabel(current, locale)}</span>
        </button>
        {open ? (
          <div className="agent-convo-scope-panel">
            <label className="agent-convo-scope-search">
              <Search size={14} aria-hidden="true" />
              <input
                ref={searchRef}
                type="search"
                value={query}
                placeholder={text.search}
                aria-label={text.search}
                autoComplete="off"
                onChange={(event) => setQuery(event.target.value)}
                onMouseDown={(event) => event.stopPropagation()}
              />
            </label>
            <ul className="agent-convo-scope-menu" role="listbox" aria-label={text.pick}>
              {visible.map((project) => {
                const selected = current.kind === "project" && current.projectId === project.project_id;
                const projectMatched = !needle
                  || project.name.toLowerCase().includes(needle)
                  || folderLabel(project.root_path).toLowerCase().includes(needle);
                const matchingAgents = projectMatched
                  ? project.agents
                  : project.agents.filter((agent) => (agent.name || agent.slug).toLowerCase().includes(needle));
                return (
                  <React.Fragment key={project.project_id}>
                    <li>
                      <button
                        type="button"
                        role="option"
                        aria-selected={selected}
                        disabled={busy}
                        onClick={() => choose({ kind: "project", projectId: project.project_id, name: project.name })}
                      >
                        <FolderKanban size={15} aria-hidden="true" />
                        <span className="agent-convo-scope-copy">
                          <strong>{project.name}</strong>
                          <small>{folderLabel(project.root_path)}</small>
                        </span>
                        {selected ? <Check className="agent-convo-scope-check" size={14} aria-hidden="true" /> : null}
                      </button>
                    </li>
                    {matchingAgents.map((agent: ProjectAgentRecord) => {
                      const agentSelected = current.kind === "agent" && current.agentId === agent.agent_id;
                      return (
                        <li key={agent.agent_id}>
                          <button
                            className="is-nested"
                            type="button"
                            role="option"
                            aria-selected={agentSelected}
                            disabled={busy}
                            onClick={() => choose({
                              kind: "agent",
                              projectId: project.project_id,
                              agentId: agent.agent_id,
                              name: agent.name || agent.slug,
                              projectName: project.name,
                            })}
                          >
                            <Bot size={15} aria-hidden="true" />
                            <span className="agent-convo-scope-copy">
                              <strong>{agent.name || agent.slug}</strong>
                              <small>{project.name}</small>
                            </span>
                            {agentSelected ? <Check className="agent-convo-scope-check" size={14} aria-hidden="true" /> : null}
                          </button>
                        </li>
                      );
                    })}
                  </React.Fragment>
                );
              })}
              {visible.length === 0 ? <li className="agent-convo-scope-empty">{text.empty}</li> : null}
            </ul>
            <div className="agent-convo-scope-footer">
              <button type="button" disabled={busy} onClick={() => void run(() => onCreateProject())}>
                <Plus size={15} aria-hidden="true" />
                {text.create}
              </button>
            </div>
          </div>
        ) : null}
        {hint ? <p className="agent-convo-hint" role="status">{hint}</p> : null}
      </div>
    </div>
  );
}
