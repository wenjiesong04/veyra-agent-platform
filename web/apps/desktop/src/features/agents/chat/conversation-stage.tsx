import * as React from "react";
import { ArrowUp, Plus, RotateCcw } from "lucide-react";
import { IconButton } from "@veyra/ui";
import type { JsonValue } from "@veyra/api-contracts";

type Locale = "zh" | "en";

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
  const scrollRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (empty) return;
    const node = scrollRef.current;
    if (!node) return;
    if (typeof node.scrollTo === "function") node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
    else node.scrollTop = node.scrollHeight;
  }, [empty, children]);

  return (
    <div {...props} className={`agent-conversation ${empty ? "is-empty" : "is-active"} ${canvasOpen ? "is-canvas" : ""} ${props.className ?? ""}`.trim()}>
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
      {canvasOpen ? canvas : null}
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
