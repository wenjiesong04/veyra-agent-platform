import { CheckCircle2, Eye, EyeOff } from "lucide-react";
import { useEffect, useState, type InputHTMLAttributes, type ReactNode } from "react";

export { authErrorMessage, errorCopy, explainAuthError } from "./auth-errors";
export type { AuthErrorExplanation, AuthErrorField, AuthErrorSurface, ErrorCopy } from "./auth-errors";

export function AuthCard({ eyebrow, title, detail, children, footer }: { eyebrow: string; title: string; detail: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <section className="auth-card">
      <div className="auth-card-heading">
        <span className="ui-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
      {children}
      {footer ? <div className="auth-card-footer">{footer}</div> : null}
    </section>
  );
}

export function FormField({ label, hint, error, invalid = false, children }: { label: string; hint?: string; error?: string; invalid?: boolean; children: ReactNode }) {
  return (
    <div className={`auth-field ${error || invalid ? "has-error" : ""}`}>
      <label>
        <span className="auth-field-label">{label}</span>
        {children}
      </label>
      {error ? <small className="auth-field-error">{error}</small> : hint ? <small>{hint}</small> : null}
    </div>
  );
}

export function PasswordInput({ showLabel, hideLabel, ...props }: InputHTMLAttributes<HTMLInputElement> & { showLabel: string; hideLabel: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <span className="password-input-wrap">
      <input {...props} type={visible ? "text" : "password"} />
      <button type="button" onClick={() => setVisible((value) => !value)} aria-label={visible ? hideLabel : showLabel} title={visible ? hideLabel : showLabel}>
        {visible ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
      </button>
    </span>
  );
}

export function FormNotice({ tone = "error", children }: { tone?: "error" | "success"; children: ReactNode }) {
  return <div className={`auth-notice ${tone}`} role={tone === "error" ? "alert" : "status"}>{tone === "success" ? <CheckCircle2 size={17} aria-hidden="true" /> : <span aria-hidden="true">!</span>}{children}</div>;
}

export function StepIndicator({ current, total, label }: { current: number; total: number; label: string }) {
  return (
    <div className="auth-progress" aria-label={`${label} ${current}/${total}`}>
      <span>{label} {current}/{total}</span>
      <div>{Array.from({ length: total }, (_, index) => <i className={index < current ? "active" : ""} key={index} />)}</div>
    </div>
  );
}

export function useCooldown(seconds = 60) {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (remaining <= 0) return;
    const timer = window.setInterval(() => setRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [remaining]);

  return { remaining, start: () => setRemaining(seconds) };
}
