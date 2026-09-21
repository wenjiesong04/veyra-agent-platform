import { MoreHorizontal, Pencil, Pin, Trash2, X, type LucideIcon } from "lucide-react";
import { projectRoutePaths, type BuilderActivityItem } from "@veyra/api-contracts";
import { Button, toast, useLocale, type NavigationGroup } from "@veyra/ui";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useProjectWorkspace } from "../../api/project-workspace";
import { agentRecentNavigation, type DesktopLocale } from "../agents/agent-navigation";
import { readSidebarResourcePins, toggleSidebarResourcePin, writeSidebarResourcePins } from "../projects/sidebar-pins";
import { notifyBuilderActivity, useBuilderActivity } from "./use-builder-activity";

type ConversationPopover = { item: BuilderActivityItem; anchor: HTMLButtonElement };
type ConversationModal =
  | { kind: "rename"; item: BuilderActivityItem }
  | { kind: "delete"; item: BuilderActivityItem }
  | null;

export function useRecentConversationNavigation({
  locale,
  projectId,
  projectName,
  projectNames,
  conversationId,
}: {
  locale: DesktopLocale;
  projectId?: string;
  projectName?: string;
  projectNames?: Record<string, string>;
  conversationId?: string;
}): { navigation: NavigationGroup; dialogs: ReactNode; conversationTitle?: string } {
  const { t } = useLocale();
  const items = useBuilderActivity();
  const [pins, setPins] = useState(readSidebarResourcePins);
  const [popover, setPopover] = useState<ConversationPopover | null>(null);
  const [modal, setModal] = useState<ConversationModal>(null);
  const pinnedIds = new Set(Object.values(pins).flatMap((entry) => entry.conversation ? [entry.conversation] : []));

  useEffect(() => { setPopover(null); }, [conversationId, projectId]);

  const ordered = [...items].sort((left, right) => Number(pinnedIds.has(right.conversation_id)) - Number(pinnedIds.has(left.conversation_id)));
  const base = agentRecentNavigation(locale, ordered, {
    projectId,
    projectName,
    projectNames,
    conversationId,
  });
  const ownerOf = (entry: BuilderActivityItem) => entry.project_id ?? projectId;
  const navigation: NavigationGroup = {
    ...base,
    items: base.items.map((item) => {
      const conversation = items.find((entry) => projectRoutePaths.projectChat(ownerOf(entry) ?? "", entry.conversation_id) === item.href);
      const ownerProjectId = conversation ? ownerOf(conversation) : undefined;
      if (!conversation || !ownerProjectId) return item;
      const open = popover?.item.conversation_id === conversation.conversation_id;
      return {
        ...item,
        trailingAction: (
          <span className="agent-row-actions">
            <button
              type="button"
              className="sidebar-more-chip"
              aria-label={`${t("conversationActions")}: ${conversation.title}`}
              title={t("conversationActions")}
              aria-haspopup="menu"
              aria-expanded={open}
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                const anchor = event.currentTarget;
                setPopover((current) => current?.item.conversation_id === conversation.conversation_id ? null : { item: conversation, anchor });
              }}
            >
              <MoreHorizontal size={15} aria-hidden="true" />
            </button>
          </span>
        ),
      };
    }),
  };
  const conversationTitle = items.find((item) => item.conversation_id === conversationId)?.title;
  const pinConversation = (item: BuilderActivityItem) => {
    const ownerProjectId = ownerOf(item);
    if (!ownerProjectId) return;
    setPopover(null);
    setPins((current) => {
      const next = toggleSidebarResourcePin(current, ownerProjectId, "conversation", item.conversation_id);
      writeSidebarResourcePins(next);
      return next;
    });
  };
  const popoverOwner = popover ? ownerOf(popover.item) : undefined;
  const dialogs = (
    <>
      {popover ? (
        <FixedSidebarPopover anchor={popover.anchor} estimatedWidth={168} className="sidebar-agent-menu" onClose={() => setPopover(null)}>
          <div className="sidebar-action-menu" role="menu" aria-label={`${t("conversationActions")}: ${popover.item.title}`}>
            <SidebarMenuItem
              icon={Pin}
              title={popoverOwner && pins[popoverOwner]?.conversation === popover.item.conversation_id ? t("unpinResource") : t("pinAgent")}
              detail={t("pinConversationDetail")}
              onClick={() => pinConversation(popover.item)}
            />
            <SidebarMenuItem
              icon={Pencil}
              title={t("editAgent")}
              detail={t("editConversationDetail")}
              onClick={() => { setPopover(null); setModal({ kind: "rename", item: popover.item }); }}
            />
            <SidebarMenuItem
              icon={Trash2}
              title={t("deleteAgent")}
              detail={t("deleteConversationDetail")}
              onClick={() => { setPopover(null); setModal({ kind: "delete", item: popover.item }); }}
              destructive
            />
          </div>
        </FixedSidebarPopover>
      ) : null}
      {modal?.kind === "rename" && ownerOf(modal.item) ? (
        <ConversationRenameDialog
          projectId={ownerOf(modal.item)!}
          item={modal.item}
          locale={locale}
          onClose={() => setModal(null)}
          onRenamed={() => notifyBuilderActivity()}
        />
      ) : null}
      {modal?.kind === "delete" && ownerOf(modal.item) ? (
        <ConversationDeleteDialog
          projectId={ownerOf(modal.item)!}
          item={modal.item}
          locale={locale}
          onClose={() => setModal(null)}
          onDeleted={() => {
            notifyBuilderActivity();
            if (conversationId === modal.item.conversation_id) {
              window.location.hash = projectRoutePaths.projectChat(ownerOf(modal.item)!);
            }
          }}
        />
      ) : null}
    </>
  );
  return { navigation, dialogs, conversationTitle };
}

function ConversationRenameDialog({
  projectId,
  item,
  locale,
  onClose,
  onRenamed,
}: {
  projectId: string;
  item: BuilderActivityItem;
  locale: DesktopLocale;
  onClose: () => void;
  onRenamed: () => void;
}) {
  const { api } = useProjectWorkspace();
  const zh = locale === "zh";
  const [title, setTitle] = useState(item.title);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);
  const copy = zh
    ? { title: "编辑聊天", name: "聊天名称", cancel: "取消", save: "保存", close: "关闭对话框", failed: "无法更新聊天名称，请重试。" }
    : { title: "Edit chat", name: "Chat name", cancel: "Cancel", save: "Save", close: "Close dialog", failed: "The chat name could not be updated. Try again." };
  useEffect(() => {
    nameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !saving) onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, saving]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!api.renameBuilderConversation) return;
    const next = title.trim();
    if (!next) return;
    setSaving(true);
    setError("");
    try {
      await api.renameBuilderConversation(projectId, item.conversation_id, { title: next });
      toast.success(zh ? "聊天名称已更新。" : "Chat renamed.");
      onRenamed();
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={saving}>
      <form className="project-form" onSubmit={(event) => void submit(event)}>
        <label>
          <span>{copy.name}</span>
          <input ref={nameRef} value={title} onChange={(event) => setTitle(event.target.value)} autoComplete="off" maxLength={80} disabled={saving} />
        </label>
        {error ? <p className="project-form-error" role="alert">{error}</p> : null}
        <div className="project-modal-actions">
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>{copy.cancel}</Button>
          <Button variant="primary" type="submit" disabled={saving || !title.trim() || !api.renameBuilderConversation}>{saving ? "…" : copy.save}</Button>
        </div>
      </form>
    </Modal>
  );
}

function ConversationDeleteDialog({
  projectId,
  item,
  locale,
  onClose,
  onDeleted,
}: {
  projectId: string;
  item: BuilderActivityItem;
  locale: DesktopLocale;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { api } = useProjectWorkspace();
  const zh = locale === "zh";
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const copy = zh
    ? { title: "移入回收站？", detail: `“${item.title}”会移入回收站，30 天内可以恢复。`, cancel: "取消", remove: "移入回收站", close: "关闭对话框", failed: "无法移入回收站，请重试。" }
    : { title: "Move chat to Trash?", detail: `“${item.title}” will stay recoverable in Trash for 30 days.`, cancel: "Cancel", remove: "Move to Trash", close: "Close dialog", failed: "The chat could not be moved to Trash. Try again." };
  const remove = async () => {
    if (!api.deleteBuilderConversation) return;
    setDeleting(true);
    setError("");
    try {
      await api.deleteBuilderConversation(projectId, item.conversation_id);
      toast.success(zh ? "已移入回收站。" : "Moved to Trash.");
      onDeleted();
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : copy.failed);
    } finally {
      setDeleting(false);
    }
  };
  return (
    <Modal title={copy.title} closeLabel={copy.close} onClose={onClose} busy={deleting}>
      <div className="project-delete-copy">
        <p>{copy.detail}</p>
        {error ? <p className="project-form-error" role="alert">{error}</p> : null}
      </div>
      <div className="project-modal-actions">
        <Button variant="ghost" onClick={onClose} disabled={deleting}>{copy.cancel}</Button>
        <Button icon={Trash2} variant="danger" onClick={() => void remove()} disabled={deleting || !api.deleteBuilderConversation}>{deleting ? "…" : copy.remove}</Button>
      </div>
    </Modal>
  );
}

function Modal({ title, closeLabel, onClose, busy, children }: { title: string; closeLabel: string; onClose: () => void; busy: boolean; children: ReactNode }) {
  return createPortal(
    <div className="project-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <div className="project-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="project-modal-header">
          <h2>{title}</h2>
          <button type="button" className="project-modal-close" onClick={onClose} aria-label={closeLabel} disabled={busy}><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

function SidebarMenuItem({ icon: Icon, title, detail, onClick, destructive = false }: { icon: LucideIcon; title: string; detail: string; onClick: () => void; destructive?: boolean }) {
  return <button className={`sidebar-popover-item ${destructive ? "is-destructive" : ""}`} type="button" role="menuitem" aria-label={title} onPointerDown={(event) => event.stopPropagation()} onMouseDown={(event) => event.stopPropagation()} onClick={(event) => { event.preventDefault(); event.stopPropagation(); onClick(); }}><span className="sidebar-popover-icon"><Icon size={15} aria-hidden="true" /></span><span className="sidebar-popover-copy"><strong>{title}</strong><small>{detail}</small></span></button>;
}

function FixedSidebarPopover({ anchor, estimatedWidth, className, onClose, children }: { anchor: HTMLButtonElement; estimatedWidth: number; className: string; onClose: () => void; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState(() => popoverPosition(anchor, estimatedWidth));
  useEffect(() => {
    const update = () => setPosition(popoverPosition(anchor, root.current?.offsetWidth || estimatedWidth));
    const onPointerDown = (event: PointerEvent) => {
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      if (path.includes(anchor) || (root.current && path.includes(root.current))) return;
      if (anchor.contains(event.target as Node) || root.current?.contains(event.target as Node)) return;
      onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    update();
    const observer = typeof ResizeObserver === "function" && root.current ? new ResizeObserver(update) : null;
    if (observer && root.current) observer.observe(root.current);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [anchor, estimatedWidth, onClose]);
  return createPortal(<div ref={root} className={`sidebar-fixed-popover ${className}`} style={position} onPointerDown={(event) => event.stopPropagation()} onMouseDown={(event) => event.stopPropagation()}>{children}</div>, document.body);
}

function popoverPosition(anchor: HTMLButtonElement, width: number): { top: number; left: number } {
  const rect = anchor.getBoundingClientRect();
  const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
  const top = rect.bottom + 6 > window.innerHeight - 120 ? Math.max(8, rect.top - 180) : rect.bottom + 6;
  return { top, left };
}
