import { forwardRef, useEffect, useState, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { BrandLoading } from "./brand-loading";
import brandIconUrl from "./assets/veyra-icon.png";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: LucideIcon;
  variant?: ButtonVariant;
  size?: ButtonSize;
};

type LinkButtonProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  icon?: LucideIcon;
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({ icon: Icon, variant = "secondary", size = "md", className = "", children, type = "button", ...props }: ButtonProps) {
  return (
    <button className={`ui-button ${variant} ${size} ${className}`.trim()} type={type} {...props}>
      {Icon ? <Icon size={size === "sm" ? 14 : 16} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function LinkButton({ icon: Icon, variant = "secondary", size = "md", className = "", children, ...props }: LinkButtonProps) {
  return (
    <a className={`ui-button ${variant} ${size} ${className}`.trim()} {...props}>
      {Icon ? <Icon size={size === "sm" ? 14 : 16} aria-hidden="true" /> : null}
      {children}
    </a>
  );
}

export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { icon: LucideIcon; label: string }>(function IconButton({ icon: Icon, label, className = "", ...props }, ref) {
  return <button ref={ref} className={`ui-icon-button ${className}`.trim()} type="button" aria-label={label} {...props}><Icon size={18} aria-hidden="true" /></button>;
});

export function Panel({ children, className = "", ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={`ui-panel ${className}`.trim()} {...props}>{children}</section>;
}

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return <span className={`ui-status ${tone}`}><span className="ui-status-dot" aria-hidden="true" />{label}</span>;
}

export function LoadingState({ label = "Loading", compact = false }: { label?: string; compact?: boolean }) {
  if (compact) {
    return <div className="ui-loading" role="status"><span className="ui-spinner" aria-hidden="true" />{label}</div>;
  }
  return <BrandLoading label={label} />;
}

export function ErrorState({ message, onRetry, retryLabel = "Retry" }: { message: string; onRetry?: () => void; retryLabel?: string }) {
  return (
    <div className="ui-error" role="alert">
      <span className="ui-error-mark" aria-hidden="true">!</span>
      <span>{message}</span>
      {onRetry ? <Button variant="ghost" size="sm" onClick={onRetry}>{retryLabel}</Button> : null}
    </div>
  );
}

export type AlertType = "success" | "warning" | "info" | "error";

const alertIcon: Record<AlertType, LucideIcon> = {
  success: CircleCheck,
  warning: TriangleAlert,
  info: Info,
  error: CircleAlert,
};

export function Alert({
  type = "info",
  title,
  description,
  closable = false,
  duration = 0,
  onClose,
  children,
  className = "",
}: {
  type?: AlertType;
  title?: string;
  description?: ReactNode;
  closable?: boolean;
  duration?: number;
  onClose?: () => void;
  children?: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(true);
  const Icon = alertIcon[type];
  useEffect(() => {
    if (!duration || duration <= 0) return;
    const timer = window.setTimeout(() => {
      setOpen(false);
      onClose?.();
    }, duration);
    return () => window.clearTimeout(timer);
  }, [duration, onClose]);
  if (!open) return null;
  return (
    <div className={`ui-alert ${type} ${className}`.trim()} role="alert">
      <span className="ui-alert-icon" aria-hidden="true"><Icon size={16} /></span>
      <div className="ui-alert-body">
        {title ? <strong className="ui-alert-title">{title}</strong> : null}
        {description ? <div className="ui-alert-description">{description}</div> : null}
        {children}
      </div>
      {closable ? <button className="ui-alert-close" type="button" aria-label="Close" onClick={() => { setOpen(false); onClose?.(); }}><X size={14} /></button> : null}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, detail, action }: { icon?: LucideIcon; title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="ui-empty">
      <span className="ui-empty-figure" aria-hidden="true">
        {Icon ? <span className="ui-empty-icon"><Icon size={28} /></span> : (
          <span className="ui-empty-mark"><img src={brandIconUrl} alt="" /></span>
        )}
      </span>
      <strong>{title}</strong>
      <p>{detail}</p>
      {action ? <div className="ui-empty-action">{action}</div> : null}
    </div>
  );
}

export function MetricCard({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail?: string; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return <div className={`ui-metric ${tone}`}><span>{label}</span><strong>{value}</strong>{detail ? <small>{detail}</small> : null}</div>;
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "good" | "warn" | "neutral" }) {
  return <span className={`ui-tag ${tone}`}>{children}</span>;
}

export function SectionHeading({ eyebrow, title, detail, action }: { eyebrow?: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="ui-section-heading">
      <div>
        {eyebrow ? <span className="ui-eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
        {detail ? <p>{detail}</p> : null}
      </div>
      {action}
    </div>
  );
}
