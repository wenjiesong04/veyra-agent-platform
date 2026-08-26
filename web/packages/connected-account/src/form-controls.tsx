import { CheckCircle2, Eye, EyeOff } from "lucide-react";
import { useEffect, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { CommunityApiError } from "./api";

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

export function FormField({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <label className={`auth-field ${error ? "has-error" : ""}`}>
      <span className="auth-field-label">{label}</span>
      {children}
      {error ? <small className="auth-field-error">{error}</small> : hint ? <small>{hint}</small> : null}
    </label>
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

type ErrorCopy = {
  invalidCredentials: string;
  registrationUnavailable: string;
  invalidCode: string;
  passwordPolicy: string;
  profileUnavailable: string;
  profileInvalid: string;
  csrf: string;
  rateLimited: string;
  network: string;
  avatarInvalid: string;
  avatarTooLarge: string;
  generic: string;
};

export function authErrorMessage(error: unknown, copy: ErrorCopy): string {
  if (!(error instanceof CommunityApiError)) return copy.generic;
  if (error.status === 429) return copy.rateLimited;
  const messages: Record<string, string> = {
    invalid_credentials: copy.invalidCredentials,
    registration_unavailable: copy.registrationUnavailable,
    invalid_verification_code: copy.invalidCode,
    password_policy_failed: copy.passwordPolicy,
    profile_update_unavailable: copy.profileUnavailable,
    profile_update_invalid: copy.profileInvalid,
    csrf_failed: copy.csrf,
    avatar_invalid: copy.avatarInvalid,
    avatar_too_large: copy.avatarTooLarge,
    network_unavailable: copy.network,
  };
  return messages[error.code] ?? (error.validationMessages[0] || copy.generic);
}

export const errorCopy = {
  zh: {
    invalidCredentials: "邮箱或密码不正确。",
    registrationUnavailable: "该邮箱已注册，或自动生成的公开标识不可用。请尝试登录。",
    invalidCode: "验证码不正确或已经过期。",
    passwordPolicy: "密码需包含 8–64 个字符。",
    profileUnavailable: "这个公开标识已被使用，请换一个。",
    profileInvalid: "请检查姓名或公开标识的格式。",
    csrf: "安全凭据已过期，请刷新页面后重试。",
    rateLimited: "操作过于频繁，请稍后再试。",
    network: "暂时无法连接社区服务，请确认服务正在运行。",
    avatarInvalid: "头像必须是有效的图片文件。",
    avatarTooLarge: "头像文件不能超过 2 MiB。",
    generic: "请求未完成，请稍后重试。",
  },
  en: {
    invalidCredentials: "The email or password is incorrect.",
    registrationUnavailable: "This email is already registered or the generated public handle is unavailable. Try signing in.",
    invalidCode: "The verification code is incorrect or has expired.",
    passwordPolicy: "Use a password of 8–64 characters.",
    profileUnavailable: "That public handle is already in use. Try another one.",
    profileInvalid: "Check the format of your name or public handle.",
    csrf: "Your security session expired. Refresh the page and try again.",
    rateLimited: "Too many attempts. Please wait and try again.",
    network: "The Community service is unavailable. Check that it is running.",
    avatarInvalid: "Choose a valid image file.",
    avatarTooLarge: "Avatar files must be 2 MiB or smaller.",
    generic: "The request could not be completed. Please try again.",
  },
} as const;
