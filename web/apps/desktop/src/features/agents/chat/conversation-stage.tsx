import * as React from "react";
import { ArrowUp, ChevronsDown, ChevronsLeft, ChevronsRight, ChevronsUp, Copy, Plus, RotateCcw } from "lucide-react";
import { IconButton, PaneResizeHandle, useLocale } from "@veyra/ui";
import type { JsonValue } from "@veyra/api-contracts";
import {
  measureConversationCanvas,
  readConversationCanvasLayout,
  writeConversationCanvasLayout,
  type ConversationCanvasSizes,
} from "./conversation-canvas-layout";

type Locale = "zh" | "en";

function conversationCanvasCopy(locale: Locale) {
  return locale === "zh"
    ? {
        collapse: "折叠画布",
        expand: "展开画布",
        resizeWidth: "调整画布宽度",
        resizeHeight: "调整画布高度",
      }
    : {
        collapse: "Collapse canvas",
        expand: "Expand canvas",
        resizeWidth: "Resize canvas",
        resizeHeight: "Resize canvas height",
      };
}

function useConversationCanvasFrame(open: boolean) {
  const stageRef = React.useRef<HTMLDivElement>(null);
  const [stored, setStored] = React.useState(readConversationCanvasLayout);
  const [box, setBox] = React.useState({ width: 0, height: 0 });
  const [collapsed, setCollapsed] = React.useState(false);
  const layout = measureConversationCanvas(box.width, box.height, stored.width, stored.height);

  React.useEffect(() => {
    if (!open) {
      setCollapsed(false);
      return;
    }
    const node = stageRef.current;
    if (!node) return;
    const sync = () => setBox({ width: node.clientWidth, height: node.clientHeight });
    sync();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(sync);
    observer.observe(node);
    return () => observer.disconnect();
  }, [open]);

  const persist = React.useCallback((patch: Partial<ConversationCanvasSizes>) => {
    setStored((current) => {
      const next = { ...current, ...patch };
      writeConversationCanvasLayout(next);
      return next;
    });
  }, []);

  return { stageRef, layout, collapsed, setCollapsed, persist };
}

export function ConversationStage({
  empty,
  canvasOpen,
  mark,
  greetingTitle,
  greetingLabel,
  greetingDetail,
  suggestions,
  contextBar,
  composer,
  canvas,
  children,
  ...props
}: {
  empty: boolean;
  canvasOpen: boolean;
  mark?: React.ReactNode;
  greetingTitle?: React.ReactNode;
  greetingLabel?: string;
  greetingDetail?: string;
  suggestions?: React.ReactNode;
  contextBar?: React.ReactNode;
  composer?: React.ReactNode;
  canvas?: React.ReactNode;
  children?: React.ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  const { locale } = useLocale();
  const labels = conversationCanvasCopy(locale);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const { stageRef, layout, collapsed, setCollapsed, persist } = useConversationCanvasFrame(canvasOpen);
  React.useEffect(() => {
    if (empty) return;
    const node = scrollRef.current;
    if (!node) return;
    if (typeof node.scrollTo === "function") node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
    else node.scrollTop = node.scrollHeight;
  }, [empty, children]);
  const canvasLayout = canvasOpen ? (layout.stacked ? "stack" : "split") : undefined;
  const FoldIcon = layout.stacked ? (collapsed ? ChevronsUp : ChevronsDown) : (collapsed ? ChevronsLeft : ChevronsRight);

  return (
    <div
      {...props}
      ref={stageRef}
      className={`agent-conversation ${empty ? "is-empty" : "is-active"} ${canvasOpen ? "is-canvas" : ""} ${props.className ?? ""}`.trim()}
      data-canvas-layout={canvasLayout}
      data-canvas-collapsed={collapsed ? "true" : undefined}
      style={{
        ...props.style,
        ...(canvasOpen
          ? {
              "--agent-convo-canvas-width": `${layout.width}px`,
              "--agent-convo-canvas-height": `${layout.height}px`,
            } as React.CSSProperties
          : undefined),
      }}
    >
      <div className="agent-conversation-main">
        {empty ? (
          <div className="agent-convo-hero">
            {mark}
            <div className="agent-convo-hero-copy">
              {greetingTitle ? <h2 {...(greetingLabel ? { "aria-label": greetingLabel } : {})}>{greetingTitle}</h2> : null}
              {greetingDetail ? <p>{greetingDetail}</p> : null}
            </div>
            {suggestions}
          </div>
        ) : (
          <div className="agent-convo-scroll" ref={scrollRef}>
            <div className="agent-convo-column">{children}</div>
          </div>
        )}
        <div className="agent-convo-dock">
          {contextBar}
          {composer}
        </div>
      </div>
      {canvasOpen && canvas ? (
        <div className={`agent-convo-canvas-slot${collapsed ? " is-collapsed" : ""}`}>
          {collapsed ? null : layout.stacked ? (
            <PaneResizeHandle
              label={labels.resizeHeight}
              edge="top"
              value={layout.height}
              min={layout.minHeight}
              max={() => measureConversationCanvas(stageRef.current?.clientWidth ?? 0, stageRef.current?.clientHeight ?? 0, layout.width, layout.height).maxHeight}
              onChange={(height) => persist({ height })}
            />
          ) : (
            <PaneResizeHandle
              label={labels.resizeWidth}
              edge="left"
              value={layout.width}
              min={layout.minWidth}
              max={() => measureConversationCanvas(stageRef.current?.clientWidth ?? 0, stageRef.current?.clientHeight ?? 0, layout.width, layout.height).maxWidth}
              onChange={(width) => persist({ width })}
            />
          )}
          <IconButton
            className="agent-convo-canvas-fold"
            icon={FoldIcon}
            label={collapsed ? labels.expand : labels.collapse}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((current) => !current)}
          />
          <div className="agent-convo-canvas-slot-body" hidden={collapsed}>{canvas}</div>
        </div>
      ) : null}
    </div>
  );
}

export function ConversationComposer({
  locale,
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
  sendLabel,
  sending,
  resetLabel,
  onReset,
  canReset,
  footerLeft,
  extraFields,
  textboxLabel,
  hideTextarea = false,
  attachLabel,
  onAttachFiles,
}: {
  locale: Locale;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  placeholder: string;
  sendLabel: string;
  sending: boolean;
  resetLabel?: string;
  onReset?: () => void;
  canReset?: boolean;
  footerLeft?: React.ReactNode;
  extraFields?: React.ReactNode;
  textboxLabel: string;
  hideTextarea?: boolean;
  attachLabel?: string;
  onAttachFiles?: (files: File[]) => void;
}) {
  const areaRef = React.useRef<HTMLTextAreaElement>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const resize = React.useCallback(() => {
    const node = areaRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(Math.max(node.scrollHeight, 24), 200)}px`;
  }, []);
  React.useEffect(() => { resize(); }, [value, resize]);
  return (
    <form
      className={`agent-convo-composer ${sending ? "is-sending" : ""}`}
      onSubmit={(event) => { event.preventDefault(); if (!disabled) onSubmit(); }}
    >
      {extraFields}
      {hideTextarea ? null : (
        <textarea
          ref={areaRef}
          aria-label={textboxLabel}
          value={value}
          placeholder={placeholder}
          rows={1}
          disabled={sending}
          onChange={(event) => onChange(event.target.value)}
          onInput={resize}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (!disabled) onSubmit();
            }
          }}
        />
      )}
      <div className="agent-convo-composer-bar">
        <div className="agent-convo-composer-meta">
          {onAttachFiles && attachLabel ? (
            <>
              <input
                ref={fileRef}
                className="agent-convo-file-input"
                type="file"
                multiple
                accept=".txt,.md,.markdown,.json,.csv,.tsv,.yaml,.yml,.html,.xml,.log,.pdf,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                tabIndex={-1}
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  event.target.value = "";
                  if (files.length) onAttachFiles(files);
                }}
              />
              <IconButton icon={Plus} label={attachLabel} disabled={sending} onClick={() => fileRef.current?.click()} />
            </>
          ) : null}
          {footerLeft}
          <span>{locale === "zh" ? "Enter 发送 · Shift+Enter 换行" : "Enter to send · Shift+Enter for a new line"}</span>
        </div>
        <div className="agent-convo-composer-actions">
          {canReset && onReset && resetLabel ? <IconButton icon={RotateCcw} label={resetLabel} onClick={onReset} /> : null}
          <button className="agent-convo-send" type="submit" aria-label={sendLabel} disabled={disabled}>
            <ArrowUp size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
    </form>
  );
}

export function ConversationTyping({ label }: { label: string }) {
  return (
    <div className="agent-convo-typing" role="status">
      <span className="agent-convo-dots" aria-hidden="true"><i /><i /><i /></span>
      <span>{label}</span>
    </div>
  );
}

function messageClock(createdAt: string, locale: Locale): string {
  if (!createdAt) return "";
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function ConversationMessageActions({
  locale,
  content,
  createdAt,
  onRetry,
}: {
  locale: Locale;
  content: string;
  createdAt?: string;
  onRetry?: () => void;
}) {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    const text = content.trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };
  const time = messageClock(createdAt ?? "", locale);
  return (
    <div className="agent-convo-actions">
      <IconButton icon={Copy} label={copied ? (locale === "zh" ? "已复制" : "Copied") : (locale === "zh" ? "复制" : "Copy")} onClick={() => void copy()} />
      {onRetry ? <IconButton icon={RotateCcw} label={locale === "zh" ? "重试" : "Retry"} onClick={onRetry} /> : null}
      {time ? <time className="agent-convo-time" dateTime={createdAt}>{time}</time> : null}
    </div>
  );
}

export function ConversationInputGrid({
  entries,
  values,
  onChange,
  fileOptions = [],
}: {
  entries: Array<[string, string]>;
  values: Record<string, JsonValue>;
  onChange: (name: string, value: JsonValue) => void;
  fileOptions?: string[];
}) {
  return (
    <div className="agent-chat-input-grid">
      {entries.map(([name, type]) => (
        <label key={name}>
          <span>{name}<small>{type}</small></span>
          {type === "boolean" ? (
            <select aria-label={name} value={String(values[name] ?? false)} onChange={(event) => onChange(name, event.target.value === "true")}>
              <option value="false">false</option>
              <option value="true">true</option>
            </select>
          ) : (
            <>
              <input
                aria-label={name}
                type={type === "integer" || type === "number" ? "number" : "text"}
                step={type === "integer" ? "1" : "any"}
                list={type === "string" && fileOptions.length > 0 && /(^|_)(path|file|document)(_|$)/i.test(name) ? `conversation-file-options-${name}` : undefined}
                value={String(values[name] ?? "")}
                onChange={(event) => onChange(name, type === "integer" ? Number.parseInt(event.target.value || "0", 10) : type === "number" ? Number.parseFloat(event.target.value || "0") : event.target.value)}
              />
              {type === "string" && fileOptions.length > 0 && /(^|_)(path|file|document)(_|$)/i.test(name) ? <datalist id={`conversation-file-options-${name}`}>{fileOptions.slice(0, 100).map((path) => <option value={path} key={path} />)}</datalist> : null}
            </>
          )}
        </label>
      ))}
    </div>
  );
}
