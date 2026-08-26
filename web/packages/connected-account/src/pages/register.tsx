import { ArrowLeft, ArrowRight, LoaderCircle, MailCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { communityAuthRoutePaths } from "@veyra/api-contracts";
import { Button, useLocale } from "@veyra/ui";
import { useAuth } from "../auth-context";
import { AuthLayout } from "../auth-layout";
import { AuthCard, FormField, FormNotice, PasswordInput, StepIndicator, authErrorMessage, errorCopy, useCooldown } from "../form-controls";

type RegisterStep = "email" | "code" | "profile";

export function RegisterPage() {
  const { locale } = useLocale();
  const { register, requestCode } = useAuth();
  const [step, setStep] = useState<RegisterStep>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cooldown = useCooldown();
  const stepNumber = step === "email" ? 1 : step === "code" ? 2 : 3;
  const copy = locale === "zh" ? {
    eyebrow: "创建账号", titles: ["先验证你的邮箱", "输入六位验证码", "完成你的个人资料"], details: ["我们会发送一个十分钟内有效的验证码。", `验证码已发送到 ${email}。`, "设置你在社区中显示的姓名和登录密码。"], step: "步骤", email: "邮箱", emailPlaceholder: "name@example.com", send: "发送验证码", sending: "正在发送", code: "验证码", codeHint: "请输入邮件中的六位数字", continue: "继续", resend: "重新发送", resendIn: "秒后可重新发送", name: "姓名", nameHint: "你可以稍后在账号设置中修改", password: "密码", passwordHint: "8–64 个字符", confirm: "确认密码", showPassword: "显示密码", hidePassword: "隐藏密码", mismatch: "两次输入的密码不一致。", create: "创建账号", creating: "正在创建", back: "返回", haveAccount: "已经有账号？", login: "登录", codeSent: "验证码已发送，请检查收件箱。",
  } : {
    eyebrow: "Create account", titles: ["Verify your email first", "Enter the six-digit code", "Finish your profile"], details: ["We will send a verification code that is valid for ten minutes.", `We sent a code to ${email}.`, "Set the name people will see and a password for sign-in."], step: "Step", email: "Email", emailPlaceholder: "name@example.com", send: "Send verification code", sending: "Sending", code: "Verification code", codeHint: "Enter the six digits from your email", continue: "Continue", resend: "Send again", resendIn: "seconds until resend", name: "Name", nameHint: "You can change this later in account settings", password: "Password", passwordHint: "8–64 characters", confirm: "Confirm password", showPassword: "Show password", hidePassword: "Hide password", mismatch: "The passwords do not match.", create: "Create account", creating: "Creating account", back: "Back", haveAccount: "Already have an account?", login: "Sign in", codeSent: "Code sent. Check your inbox.",
  };
  const title = copy.titles[stepNumber - 1] ?? copy.titles[0];
  const detail = copy.details[stepNumber - 1] ?? copy.details[0];

  async function sendCode() {
    setSubmitting(true);
    setError(null);
    try {
      await requestCode(email, "registration");
      cooldown.start();
      setStep("code");
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

  function onCodeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code)) return;
    setError(null);
    setStep("profile");
  }

  async function onProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirmation) {
      setError(copy.mismatch);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await register({ email, verification_code: code, display_name: displayName, password });
      window.location.hash = communityAuthRoutePaths.account;
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <AuthCard eyebrow={copy.eyebrow} title={title} detail={detail} footer={<p>{copy.haveAccount} <a href={communityAuthRoutePaths.login}>{copy.login}</a></p>}>
        <StepIndicator current={stepNumber} total={3} label={copy.step} />
        {step === "email" ? <form className="auth-form" onSubmit={onEmailSubmit}><FormField label={copy.email}><input autoFocus autoComplete="email" inputMode="email" name="email" placeholder={copy.emailPlaceholder} required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></FormField>{error ? <FormNotice>{error}</FormNotice> : null}<Button className="auth-submit" type="submit" variant="primary" disabled={submitting} icon={submitting ? LoaderCircle : MailCheck}>{submitting ? copy.sending : copy.send}</Button></form> : null}
        {step === "code" ? <form className="auth-form" onSubmit={onCodeSubmit}><FormNotice tone="success">{copy.codeSent}</FormNotice><FormField label={copy.code} hint={copy.codeHint}><input autoFocus className="verification-code-input" autoComplete="one-time-code" inputMode="numeric" maxLength={6} pattern="[0-9]{6}" required value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></FormField>{error ? <FormNotice>{error}</FormNotice> : null}<Button className="auth-submit" type="submit" variant="primary" disabled={code.length !== 6} icon={ArrowRight}>{copy.continue}</Button><div className="auth-secondary-actions"><Button type="button" variant="ghost" icon={ArrowLeft} onClick={() => { setError(null); setStep("email"); }}>{copy.back}</Button><Button type="button" variant="ghost" disabled={cooldown.remaining > 0 || submitting} onClick={() => void sendCode()}>{cooldown.remaining > 0 ? `${cooldown.remaining} ${copy.resendIn}` : copy.resend}</Button></div></form> : null}
        {step === "profile" ? <form className="auth-form" onSubmit={onProfileSubmit}><FormField label={copy.name} hint={copy.nameHint}><input autoFocus autoComplete="name" maxLength={80} name="display-name" required value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></FormField><FormField label={copy.password} hint={copy.passwordHint}><PasswordInput autoComplete="new-password" minLength={8} maxLength={64} name="password" required value={password} onChange={(event) => setPassword(event.target.value)} showLabel={copy.showPassword} hideLabel={copy.hidePassword} /></FormField><FormField label={copy.confirm}><PasswordInput autoComplete="new-password" minLength={8} maxLength={64} name="password-confirmation" required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} showLabel={copy.showPassword} hideLabel={copy.hidePassword} /></FormField>{error ? <FormNotice>{error}</FormNotice> : null}<Button className="auth-submit" type="submit" variant="primary" disabled={submitting} icon={submitting ? LoaderCircle : ArrowRight}>{submitting ? copy.creating : copy.create}</Button><Button type="button" variant="ghost" icon={ArrowLeft} onClick={() => { setError(null); setStep("code"); }}>{copy.back}</Button></form> : null}
      </AuthCard>
    </AuthLayout>
  );
}
