import { ArrowRight, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { communityAuthRoutePaths } from "@veyra/api-contracts";
import { Button, LinkButton, useLocale } from "@veyra/ui";
import { AuthLayout } from "../auth/auth-layout";
import { useAuth } from "../auth/auth-context";
import { AuthCard, FormField, FormNotice, PasswordInput, authErrorMessage, errorCopy } from "../auth/form-controls";

export function LoginPage() {
  const { locale } = useLocale();
  const { account, login, status } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = locale === "zh" ? {
    eyebrow: "账号登录", title: "欢迎回来", detail: "使用你的邮箱和密码登录 Veyra Community。", email: "邮箱", emailPlaceholder: "name@example.com", password: "密码", showPassword: "显示密码", hidePassword: "隐藏密码", forgot: "忘记密码？", submit: "登录", submitting: "正在登录", noAccount: "还没有账号？", register: "创建账号", signedIn: "你已经登录", signedInDetail: `当前账号：${account?.email ?? ""}`, account: "进入账号设置",
  } : {
    eyebrow: "Account sign in", title: "Welcome back", detail: "Sign in to Veyra Community with your email and password.", email: "Email", emailPlaceholder: "name@example.com", password: "Password", showPassword: "Show password", hidePassword: "Hide password", forgot: "Forgot password?", submit: "Sign in", submitting: "Signing in", noAccount: "New to Veyra?", register: "Create an account", signedIn: "You are already signed in", signedInDetail: `Current account: ${account?.email ?? ""}`, account: "Open account settings",
  };

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      window.location.hash = communityAuthRoutePaths.account;
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
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
          <form className="auth-form" onSubmit={onSubmit}>
            <FormField label={copy.email}>
              <input autoComplete="email" inputMode="email" name="email" placeholder={copy.emailPlaceholder} required type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
            </FormField>
            <FormField label={copy.password}>
              <PasswordInput autoComplete="current-password" minLength={12} name="password" required value={password} onChange={(event) => setPassword(event.target.value)} showLabel={copy.showPassword} hideLabel={copy.hidePassword} />
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
