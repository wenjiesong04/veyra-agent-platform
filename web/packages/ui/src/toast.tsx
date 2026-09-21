import { CircleAlert, CircleCheck, Info, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocale } from "./i18n";

export type ToastTone = "success" | "warning" | "info" | "error";

export type ToastInput = {
  message: string;
  tone?: ToastTone;
  duration?: number;
  closable?: boolean;
};

type ToastRecord = {
  id: string;
  message: string;
  tone: ToastTone;
  duration: number;
  closable: boolean;
};

type Listener = (toasts: ToastRecord[]) => void;

const listeners = new Set<Listener>();
let toasts: ToastRecord[] = [];
const timers = new Map<string, number>();

const toastIcon: Record<ToastTone, LucideIcon> = {
  success: CircleCheck,
  warning: TriangleAlert,
  info: Info,
  error: CircleAlert,
};

function emit(): void {
  listeners.forEach((listener) => listener(toasts));
}

function nextId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function dismissToast(id: string): void {
  const timer = timers.get(id);
  if (timer !== undefined) {
    window.clearTimeout(timer);
    timers.delete(id);
  }
  const next = toasts.filter((item) => item.id !== id);
  if (next.length === toasts.length) return;
  toasts = next;
  emit();
}

export function clearToasts(): void {
  timers.forEach((timer) => window.clearTimeout(timer));
  timers.clear();
  toasts = [];
  emit();
}

function pushToast(input: string | ToastInput): string {
  const payload = typeof input === "string" ? { message: input } : input;
  const tone = payload.tone ?? "info";
  const record: ToastRecord = {
    id: nextId(),
    message: payload.message,
    tone,
    duration: payload.duration ?? (tone === "error" ? 5_000 : 3_200),
    closable: payload.closable ?? tone === "error",
  };
  toasts = [...toasts, record];
  emit();
  if (record.duration > 0 && typeof window !== "undefined") {
    timers.set(record.id, window.setTimeout(() => dismissToast(record.id), record.duration));
  }
  return record.id;
}

export const toast = Object.assign(pushToast, {
  success: (message: string) => pushToast({ message, tone: "success" }),
  warning: (message: string) => pushToast({ message, tone: "warning" }),
  info: (message: string) => pushToast({ message, tone: "info" }),
  error: (message: string) => pushToast({ message, tone: "error", duration: 5_000, closable: true }),
  dismiss: dismissToast,
  clear: clearToasts,
});

export function ToastHost() {
  const { t } = useLocale();
  const [items, setItems] = useState<ToastRecord[]>(toasts);

  useEffect(() => {
    listeners.add(setItems);
    setItems(toasts);
    return () => {
      listeners.delete(setItems);
      if (listeners.size === 0) clearToasts();
    };
  }, []);

  if (typeof document === "undefined" || items.length === 0) return null;

  return createPortal(
    <div className="ui-toast-host" aria-live="polite" aria-relevant="additions">
      {items.map((item) => {
        const Icon = toastIcon[item.tone];
        return (
          <div className={`ui-toast ${item.tone}`} role={item.tone === "error" ? "alert" : "status"} key={item.id}>
            <span className="ui-toast-icon" aria-hidden="true"><Icon size={16} /></span>
            <span className="ui-toast-message">{item.message}</span>
            {item.closable ? (
              <button className="ui-toast-close" type="button" aria-label={t("closeToast")} onClick={() => dismissToast(item.id)}>
                <X size={14} />
              </button>
            ) : null}
          </div>
        );
      })}
    </div>,
    document.body,
  );
}
