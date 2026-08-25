import type { AnchorHTMLAttributes, ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

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

export function IconButton({ icon: Icon, label, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { icon: LucideIcon; label: string }) {
  return (
    <button className={`ui-icon-button ${className}`.trim()} type="button" aria-label={label} {...props}>
      <Icon size={18} aria-hidden="true" />
    </button>
  );
}

export function Panel({ children, className = "", ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={`ui-panel ${className}`.trim()} {...props}>{children}</section>;
}

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return <span className={`ui-status ${tone}`}><span className="ui-status-dot" aria-hidden="true" />{label}</span>;
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return <div className="ui-loading" role="status"><span className="ui-spinner" aria-hidden="true" />{label}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="ui-error" role="alert">
      <span className="ui-error-mark" aria-hidden="true">!</span>
      <span>{message}</span>
      {onRetry ? <Button variant="ghost" size="sm" onClick={onRetry}>Retry</Button> : null}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, detail, action }: { icon?: LucideIcon; title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="ui-empty">
      {Icon ? <span className="ui-empty-icon"><Icon size={20} aria-hidden="true" /></span> : null}
      <strong>{title}</strong>
      <p>{detail}</p>
      {action}
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
