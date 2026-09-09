import { ArrowRight, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { communityAuthRoutePaths, desktopPathAfterAuth } from "@veyra/api-contracts";
import { Button, LinkButton, useLocale } from "@veyra/ui";
import { useAuth } from "../auth-context";
import { AuthLayout } from "../auth-layout";
import { AuthCard, FormField, FormNotice, PasswordInput, errorCopy, explainAuthError } from "../form-controls";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FieldErrors = { email?: string; password?: string };

export function LoginPage({ afterAuthHref = communityAuthRoutePaths.account }: { afterAuthHref?: string } = {}) {
  const { locale } = useLocale();
  const { account, login, status } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [passwordInvalid, setPasswordInvalid] = useState(false);
  const copy = locale === "zh" ? {
    eyebrow: "账号登录", title: "欢迎回来", detail: "使用你的邮箱和密码登录 Veyra。", email: "邮箱", emailPlaceholder: "name@example.com", emailRequired: "请输入邮箱。", emailInvalid: "请输入有效的邮箱地址。", password: "密码", passwordRequired: "请输入密码。", passwordMin: "密码至少 8 个字符。", showPassword: "显示密码", hidePassword: "隐藏密码", forgot: "忘记密码？", submit: "登录", submitting: "正在登录", noAccount: "还没有账号？", register: "创建账号", signedIn: "你已经登录", signedInDetail: `当前账号：${account?.email ?? ""}`, account: "进入账号设置",
  } : {
    eyebrow: "Account sign in", title: "Welcome back", detail: "Sign in to Veyra with your email and password.", email: "Email", emailPlaceholder: "name@example.com", emailRequired: "Email is required.", emailInvalid: "Enter a valid email address.", password: "Password", passwordRequired: "Password is required.", passwordMin: "Password must be at least 8 characters.", showPassword: "Show password", hidePassword: "Hide password", forgot: "Forgot password?", submit: "Sign in", submitting: "Signing in", noAccount: "New to Veyra?", register: "Create an account", signedIn: "You are already signed in", signedInDetail: `Current account: ${account?.email ?? ""}`, account: "Open account settings",
  };

  function validateFields(): FieldErrors {
    const next: FieldErrors = {};
    if (!email.trim()) next.email = copy.emailRequired;
    else if (!EMAIL_PATTERN.test(email.trim())) next.email = copy.emailInvalid;
    if (!password) next.password = copy.passwordRequired;
    else if (password.length < 8) next.password = copy.passwordMin;
    return next;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextFieldErrors = validateFields();
    setFieldErrors(nextFieldErrors);
    setPasswordInvalid(false);
    setError(null);
    if (Object.keys(nextFieldErrors).length > 0) return;
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      window.location.hash = desktopPathAfterAuth(window.location.hash, afterAuthHref);
    } catch (caught) {
      const explained = explainAuthError(caught, errorCopy[locale], "login");
      setPasswordInvalid(explained.field === "password");
      setError(explained.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <AuthCard
        eyebrow={copy.eyebrow}
        title={account ? copy.signedIn : copy.title}
        detail={account ? copy.signedInDetail : copy.detail}
        footer={!account ? <p>{copy.noAccount} <a href={communityAuthRoutePaths.register}>{copy.register}</a></p> : undefined}
      >
        {account ? <LinkButton className="auth-submit" href={communityAuthRoutePaths.account} icon={ArrowRight} variant="primary">{copy.account}</LinkButton> : (
          <form className="auth-form" noValidate onSubmit={onSubmit}>
            <FormField label={copy.email} error={fieldErrors.email}>
              <input aria-invalid={Boolean(fieldErrors.email)} autoComplete="email" inputMode="email" name="email" placeholder={copy.emailPlaceholder} required type="email" value={email} onChange={(event) => { setEmail(event.target.value); setFieldErrors((current) => ({ ...current, email: undefined })); }} />
            </FormField>
            <FormField label={copy.password} error={fieldErrors.password} invalid={passwordInvalid}>
              <PasswordInput aria-invalid={Boolean(fieldErrors.password) || passwordInvalid} autoComplete="current-password" minLength={8} name="password" required value={password} onChange={(event) => { setPassword(event.target.value); setFieldErrors((current) => ({ ...current, password: undefined })); setPasswordInvalid(false); }} showLabel={copy.showPassword} hideLabel={copy.hidePassword} />
            </FormField>
            <div className="auth-form-row"><a href={communityAuthRoutePaths.forgotPassword}>{copy.forgot}</a></div>
            {error ? <FormNotice>{error}</FormNotice> : null}
            <Button className="auth-submit" type="submit" variant="primary" disabled={submitting || status === "booting"} icon={submitting ? LoaderCircle : ArrowRight}>{submitting ? copy.submitting : copy.submit}</Button>
          </form>
        )}
      </AuthCard>
    </AuthLayout>
  );
}
