import { ArrowLeft, ArrowRight, CheckCircle2, LoaderCircle, MailCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { communityAuthRoutePaths } from "@veyra/api-contracts";
import { Button, LinkButton, useLocale } from "@veyra/ui";
import { AuthLayout } from "../auth/auth-layout";
import { useAuth } from "../auth/auth-context";
import { AuthCard, FormField, FormNotice, PasswordInput, StepIndicator, authErrorMessage, errorCopy, useCooldown } from "../auth/form-controls";

type ResetStep = "email" | "reset" | "done";

export function ForgotPasswordPage() {
  const { locale } = useLocale();
  const { requestCode, resetPassword } = useAuth();
  const [step, setStep] = useState<ResetStep>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cooldown = useCooldown();
  const copy = locale === "zh" ? {
    eyebrow: "找回密码", title: "重置你的密码", detail: "先验证注册邮箱，再设置一个新密码。", resetTitle: "输入验证码和新密码", resetDetail: `验证码已发送到 ${email}。`, doneTitle: "密码已更新", doneDetail: "旧会话已退出。现在可以使用新密码登录。", step: "步骤", email: "邮箱", emailPlaceholder: "name@example.com", send: "发送重置验证码", sending: "正在发送", code: "验证码", codeHint: "请输入邮件中的六位数字", password: "新密码", passwordHint: "8–64 个字符", confirm: "确认新密码", showPassword: "显示密码", hidePassword: "隐藏密码", mismatch: "两次输入的密码不一致。", reset: "更新密码", resetting: "正在更新", resend: "重新发送", resendIn: "秒后可重新发送", back: "返回登录", login: "使用新密码登录", sent: "如果该邮箱已注册，你会收到一封验证码邮件。",
  } : {
    eyebrow: "Password recovery", title: "Reset your password", detail: "Verify your registered email, then choose a new password.", resetTitle: "Enter the code and a new password", resetDetail: `We sent a code to ${email}.`, doneTitle: "Password updated", doneDetail: "Older sessions have been signed out. You can now use the new password.", step: "Step", email: "Email", emailPlaceholder: "name@example.com", send: "Send reset code", sending: "Sending", code: "Verification code", codeHint: "Enter the six digits from your email", password: "New password", passwordHint: "8–64 characters", confirm: "Confirm new password", showPassword: "Show password", hidePassword: "Hide password", mismatch: "The passwords do not match.", reset: "Update password", resetting: "Updating", resend: "Send again", resendIn: "seconds until resend", back: "Back to sign in", login: "Sign in with the new password", sent: "If the email is registered, a verification message is on its way.",
  };

  async function sendCode() {
    setSubmitting(true);
    setError(null);
    try {
      await requestCode(email, "password_reset");
      cooldown.start();
      setStep("reset");
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setSubmitting(false);
    }
  }

  async function onEmailSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendCode();
  }

  async function onResetSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirmation) {
      setError(copy.mismatch);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await resetPassword({ email, verification_code: code, new_password: password });
      setStep("done");
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setSubmitting(false);
    }
  }

  const title = step === "reset" ? copy.resetTitle : step === "done" ? copy.doneTitle : copy.title;
  const detail = step === "reset" ? copy.resetDetail : step === "done" ? copy.doneDetail : copy.detail;
  return (
    <AuthLayout>
      <AuthCard eyebrow={copy.eyebrow} title={title} detail={detail} footer={step !== "done" ? <p><a href={communityAuthRoutePaths.login}>{copy.back}</a></p> : undefined}>
        {step !== "done" ? <StepIndicator current={step === "email" ? 1 : 2} total={2} label={copy.step} /> : null}
        {step === "email" ? (
          <form className="auth-form" onSubmit={onEmailSubmit}>
            <FormField label={copy.email}><input autoFocus autoComplete="email" inputMode="email" name="email" placeholder={copy.emailPlaceholder} required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></FormField>
            {error ? <FormNotice>{error}</FormNotice> : null}
            <Button className="auth-submit" type="submit" variant="primary" disabled={submitting} icon={submitting ? LoaderCircle : MailCheck}>{submitting ? copy.sending : copy.send}</Button>
          </form>
        ) : null}
        {step === "reset" ? (
          <form className="auth-form" onSubmit={onResetSubmit}>
            <FormNotice tone="success">{copy.sent}</FormNotice>
            <FormField label={copy.code} hint={copy.codeHint}><input autoFocus className="verification-code-input" autoComplete="one-time-code" inputMode="numeric" maxLength={6} pattern="[0-9]{6}" required value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></FormField>
            <FormField label={copy.password} hint={copy.passwordHint}><PasswordInput autoComplete="new-password" minLength={8} maxLength={64} name="new-password" required value={password} onChange={(event) => setPassword(event.target.value)} showLabel={copy.showPassword} hideLabel={copy.hidePassword} /></FormField>
            <FormField label={copy.confirm}><PasswordInput autoComplete="new-password" minLength={8} maxLength={64} name="new-password-confirmation" required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} showLabel={copy.showPassword} hideLabel={copy.hidePassword} /></FormField>
            {error ? <FormNotice>{error}</FormNotice> : null}
            <Button className="auth-submit" type="submit" variant="primary" disabled={submitting || code.length !== 6} icon={submitting ? LoaderCircle : ArrowRight}>{submitting ? copy.resetting : copy.reset}</Button>
            <div className="auth-secondary-actions">
              <Button type="button" variant="ghost" icon={ArrowLeft} onClick={() => { setError(null); setStep("email"); }}>{copy.back}</Button>
              <Button type="button" variant="ghost" disabled={cooldown.remaining > 0 || submitting} onClick={() => void sendCode()}>{cooldown.remaining > 0 ? `${cooldown.remaining} ${copy.resendIn}` : copy.resend}</Button>
            </div>
          </form>
        ) : null}
        {step === "done" ? <div className="auth-success-state"><CheckCircle2 size={36} aria-hidden="true" /><LinkButton className="auth-submit" href={communityAuthRoutePaths.login} icon={ArrowRight} variant="primary">{copy.login}</LinkButton></div> : null}
      </AuthCard>
    </AuthLayout>
  );
}
