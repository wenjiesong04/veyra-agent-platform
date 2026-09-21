import { BookOpen, Bot, FolderKanban, MessageCircle, Package, RotateCcw, Trash2, Workflow, X, type LucideIcon } from "lucide-react";
import type { WorkspaceTrashItem, WorkspaceTrashKind } from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, ListSkeleton, LoadingMask, Panel, SectionHeading, StatusBadge, Tag, toast, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { LocalApiClientError } from "../api/local-client";
import { useProjectWorkspace } from "../api/project-workspace";
import { relativeActivityTime } from "../features/agents/agent-navigation";
import { notifyBuilderActivity } from "../features/builder/use-builder-activity";

const kindIcons: Record<WorkspaceTrashKind, LucideIcon> = {
  project: FolderKanban,
  agent: Bot,
  workflow: Workflow,
  knowledge: BookOpen,
  conversation: MessageCircle,
  plugin: Package,
};

export function TrashPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { api, refresh } = useProjectWorkspace();
  const [items, setItems] = useState<WorkspaceTrashItem[]>([]);
  const [retentionDays, setRetentionDays] = useState(30);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [purgeItem, setPurgeItem] = useState<WorkspaceTrashItem | null>(null);
  const copy = zh ? {
    eyebrow: "本机回收区",
    title: "已删除的工作区对象会在这里保留 30 天。",
    description: "项目、Agent、工作流、知识、聊天和插件卸载包都可以恢复；永久删除需要再次确认，且不可撤销。",
    retention: "默认保留 30 天",
    empty: "回收站是空的",
    emptyDetail: "从侧栏删除的项目、Agent、工作流、知识或聊天会出现在这里。",
    unavailable: "当前工作区无法打开回收站。",
    failed: "无法加载回收站，请检查本机 sidecar。",
    restoreFailed: "无法恢复该项。",
    purgeFailed: "无法永久删除该项。",
    restore: "恢复",
    restoreBlocked: "所属项目仍在回收站中，需先恢复项目。",
    purge: "永久删除",
    refresh: "刷新",
    loading: "正在加载回收站…",
    restored: "已恢复。",
    purged: "已永久删除。",
    count: "项",
    removed: "移入时间",
    expires: "到期",
    daysLeft: "天后清除",
    project: "所属项目",
    purgeTitle: "永久删除？",
    purgeDetail: (name: string) => `将永久删除“${name}”，无法恢复。`,
    cancel: "取消",
    close: "关闭对话框",
    kinds: { project: "项目", agent: "Agent", workflow: "工作流", knowledge: "知识", conversation: "聊天", plugin: "插件" } satisfies Record<WorkspaceTrashKind, string>,
  } : {
    eyebrow: "Local trash",
    title: "Deleted workspace objects stay recoverable for 30 days.",
    description: "Projects, Agents, Workflows, Knowledge, chats, and uninstalled plugin packs can be restored. Permanent delete needs a second confirmation.",
    retention: "Kept for 30 days",
    empty: "Trash is empty",
    emptyDetail: "Projects, Agents, Workflows, Knowledge, and chats moved from the sidebar appear here.",
    unavailable: "This workspace cannot open Trash.",
    failed: "Trash could not be loaded. Check the desktop sidecar.",
    restoreFailed: "That item could not be restored.",
    purgeFailed: "That item could not be permanently deleted.",
    restore: "Restore",
    restoreBlocked: "Restore the parent Project first.",
    purge: "Delete forever",
    refresh: "Refresh",
    loading: "Loading trash…",
    restored: "Restored.",
    purged: "Permanently deleted.",
    count: "items",
    removed: "Removed",
    expires: "Expires",
    daysLeft: "days left",
    project: "Project",
    purgeTitle: "Delete forever?",
    purgeDetail: (name: string) => `This permanently deletes “${name}” and cannot be undone.`,
    cancel: "Cancel",
    close: "Close dialog",
    kinds: { project: "Project", agent: "Agent", workflow: "Workflow", knowledge: "Knowledge", conversation: "Chat", plugin: "Plugin" } satisfies Record<WorkspaceTrashKind, string>,
  };

  const load = useCallback(async () => {
    if (!api.listWorkspaceTrash) {
      setStatus("error");
      setError(copy.unavailable);
      setItems([]);
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const listed = await api.listWorkspaceTrash();
      setItems(listed.items);
      setRetentionDays(listed.retention_days);
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(trashLoadError(cause, copy.failed));
    }
  }, [api, copy.failed, copy.unavailable]);

  useEffect(() => { void load(); }, [load]);

  const actionError = (cause: unknown, fallback: string) => (
    cause instanceof LocalApiClientError ? cause.message : cause instanceof Error ? cause.message : fallback
  );

  async function restore(item: WorkspaceTrashItem) {
    if (!api.restoreWorkspaceTrash || !item.restorable) return;
    setBusyId(`${item.kind}:${item.id}`);
    setError("");
    try {
      await api.restoreWorkspaceTrash(item.kind, item.id);
      toast.success(copy.restored);
      if (item.kind === "conversation") notifyBuilderActivity();
      if (item.kind !== "plugin") await refresh();
      await load();
    } catch (cause) {
      toast.error(actionError(cause, copy.restoreFailed));
    } finally {
      setBusyId(null);
    }
  }

  async function purge(item: WorkspaceTrashItem) {
    if (!api.purgeWorkspaceTrash) return;
    setBusyId(`${item.kind}:${item.id}`);
    setError("");
    try {
      await api.purgeWorkspaceTrash(item.kind, item.id);
      setPurgeItem(null);
      toast.success(copy.purged);
      if (item.kind !== "plugin") await refresh();
      await load();
    } catch (cause) {
      toast.error(actionError(cause, copy.purgeFailed));
    } finally {
      setBusyId(null);
    }
  }

  if (status === "loading" && items.length === 0) {
    return (
      <div className="page-stack">
        <div className="page-intro">
          <div>
            <span className="ui-eyebrow">{copy.eyebrow}</span>
            <h2>{copy.title}</h2>
            <p>{copy.description}</p>
          </div>
        </div>
        <Panel><ListSkeleton label={copy.loading} /></Panel>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="intro-actions">
          <StatusBadge label={`${retentionDays} · ${copy.retention}`} tone="good" />
          <Button icon={RotateCcw} variant="ghost" onClick={() => void load()} disabled={status === "loading"}>{copy.refresh}</Button>
        </div>
      </div>
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {items.length === 0 && status === "error" ? null : items.length === 0 ? (
        <Panel><EmptyState icon={Trash2} title={copy.empty} detail={copy.emptyDetail} /></Panel>
      ) : (
        <Panel>
          <SectionHeading eyebrow={copy.eyebrow} title={`${items.length} ${copy.count}`} />
          <LoadingMask active={busyId !== null} label={copy.loading}>
          <div className="trash-list">
            {items.map((item) => {
              const Icon = kindIcons[item.kind];
              const id = `${item.kind}:${item.id}`;
              const busy = busyId === id;
              return (
                <article className="trash-item" key={id}>
                  <span className="row-icon"><Icon size={17} aria-hidden="true" /></span>
                  <span className="row-copy">
                    <strong>{item.name}</strong>
                    <small>
                      {copy.removed} {relativeActivityTime(item.removed_at, locale)}
                      {item.project_name ? ` · ${copy.project} ${item.project_name}` : ""}
                      {` · ${copy.expires} ${remainingDays(item.expires_at)} ${copy.daysLeft}`}
                    </small>
                    {!item.restorable ? <small className="trash-blocked">{copy.restoreBlocked}</small> : null}
                  </span>
                  <Tag>{copy.kinds[item.kind]}</Tag>
                  <span className="trash-item-actions">
                    <Button size="sm" variant="secondary" disabled={busy || !item.restorable || !api.restoreWorkspaceTrash} onClick={() => void restore(item)}>{copy.restore}</Button>
                    <Button size="sm" variant="danger" disabled={busy || !api.purgeWorkspaceTrash} onClick={() => setPurgeItem(item)}>{copy.purge}</Button>
                  </span>
                </article>
              );
            })}
          </div>
          </LoadingMask>
        </Panel>
      )}
      {purgeItem ? (
        <PurgeDialog
          title={copy.purgeTitle}
          detail={copy.purgeDetail(purgeItem.name)}
          cancel={copy.cancel}
          confirm={copy.purge}
          close={copy.close}
          busy={busyId === `${purgeItem.kind}:${purgeItem.id}`}
          onClose={() => { if (!busyId) setPurgeItem(null); }}
          onConfirm={() => void purge(purgeItem)}
        />
      ) : null}
    </div>
  );
}

function trashLoadError(cause: unknown, fallback: string): string {
  if (cause instanceof LocalApiClientError && (cause.status === 404 || cause.status === 405 || cause.message === "Not Found")) {
    return fallback;
  }
  return cause instanceof Error && cause.message.trim() ? cause.message : fallback;
}

function remainingDays(expiresAt: string, now = Date.now()): number {
  const stamp = Date.parse(expiresAt);
  if (!Number.isFinite(stamp)) return 0;
  return Math.max(0, Math.ceil((stamp - now) / 86_400_000));
}

function PurgeDialog({
  title,
  detail,
  cancel,
  confirm,
  close,
  busy,
  onClose,
  onConfirm,
}: {
  title: string;
  detail: string;
  cancel: string;
  confirm: string;
  close: string;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return createPortal(
    <div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <div className="project-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="project-modal-header">
          <h2>{title}</h2>
          <button type="button" className="project-modal-close" onClick={onClose} aria-label={close} disabled={busy}><X size={18} /></button>
        </div>
        <div className="project-delete-copy">
          <p>{detail}</p>
        </div>
        <div className="project-modal-actions">
          <Button variant="ghost" onClick={onClose} disabled={busy}>{cancel}</Button>
          <Button icon={Trash2} variant="danger" onClick={onConfirm} disabled={busy}>{busy ? "…" : confirm}</Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
