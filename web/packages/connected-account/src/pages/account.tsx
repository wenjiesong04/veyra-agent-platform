import { Check, ImagePlus, KeyRound, LoaderCircle, LogIn, LogOut, MonitorSmartphone, Save, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { communityAuthRoutePaths, type CommunityDeviceSession } from "@veyra/api-contracts";
import { Button, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, useLocale } from "@veyra/ui";
import { useAuth } from "../auth-context";
import { FormField, FormNotice, authErrorMessage, errorCopy } from "../form-controls";

const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

function formatDate(value: string, locale: "zh" | "en"): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function ConnectedAccountPage() {
  const { locale } = useLocale();
  const { account, bootstrapError, deleteAvatar, listSessions, logout, replaceAvatar, revokeSession, status, updateProfile } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [handle, setHandle] = useState("");
  const [sessions, setSessions] = useState<CommunityDeviceSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const copy = locale === "zh" ? {
    eyebrow: "社区身份", title: "管理你的 Veyra 账号", description: "账号用于发布、评审和保留来源关系；Agent 仍在你的本机运行。", connected: "已登录", loading: "正在读取账号", signedOut: "尚未登录", signedOutDetail: "无需账号也可以浏览社区。登录后可以管理个人资料、设备和发布身份。", login: "登录", register: "创建账号", benefits: ["发布不可变版本", "保存与评审条目", "保留 Fork 来源关系"], boundary: "安全边界", public: "公共账号，本机执行", boundaryDetail: "Community 保存账号和发布元数据，不会在服务器上执行你的 Agent。", profile: "个人资料", profileDetail: "姓名会显示在社区中，公开标识用于创作者页面。", name: "姓名", handle: "公开标识", handleHint: "3–32 位小写字母、数字或连字符", email: "登录邮箱", save: "保存修改", saving: "正在保存", saved: "个人资料已更新。", avatar: "头像", avatarDetail: "头像会保存到 Community 账号，不会写入本地源文件。", chooseAvatar: "选择头像", replaceAvatar: "替换头像", removeAvatar: "删除头像", removingAvatar: "正在删除", avatarPreview: "头像预览", devices: "登录设备", devicesDetail: "查看账号会话，并撤销不再使用的设备。", current: "当前设备", lastActive: "最后活动", expires: "过期时间", revoke: "撤销", revoking: "正在撤销", noSessions: "没有可显示的登录设备。", signOut: "退出当前账号", signingOut: "正在退出", accountUnavailable: "暂时无法检查登录状态。你仍然可以浏览社区。", avatarSaved: "头像已更新。", avatarRemoved: "头像已删除。", invalidAvatar: "请选择 PNG、JPEG 或 WebP 图片。", avatarTooLarge: "头像文件不能超过 2 MiB。",
  } : {
    eyebrow: "Community identity", title: "Manage your Veyra account", description: "Your account is for publishing, reviews, and lineage. Agents still run on your device.", connected: "Signed in", loading: "Loading account", signedOut: "You are not signed in", signedOutDetail: "You can browse Community without an account. Sign in to manage your profile, devices, and publishing identity.", login: "Sign in", register: "Create account", benefits: ["Publish immutable versions", "Save and review entries", "Keep Fork lineage"], boundary: "Security boundary", public: "Public account, local execution", boundaryDetail: "Community stores account and publication metadata. It does not execute your Agents on the server.", profile: "Profile", profileDetail: "Your name appears in Community. Your public handle identifies your creator page.", name: "Name", handle: "Public handle", handleHint: "3–32 lowercase letters, numbers, or hyphens", email: "Sign-in email", save: "Save changes", saving: "Saving", saved: "Profile updated.", avatar: "Avatar", avatarDetail: "Your avatar is stored with your Community account, never in local source files.", chooseAvatar: "Choose avatar", replaceAvatar: "Replace avatar", removeAvatar: "Remove avatar", removingAvatar: "Removing", avatarPreview: "Avatar preview", devices: "Signed-in devices", devicesDetail: "Review account sessions and revoke devices you no longer use.", current: "Current device", lastActive: "Last active", expires: "Expires", revoke: "Revoke", revoking: "Revoking", noSessions: "There are no sign-in devices to display.", signOut: "Sign out of this account", signingOut: "Signing out", accountUnavailable: "We could not check your sign-in state. You can still browse Community.", avatarSaved: "Avatar updated.", avatarRemoved: "Avatar removed.", invalidAvatar: "Choose a PNG, JPEG, or WebP image.", avatarTooLarge: "Avatar files must be 2 MiB or smaller.",
  };

  useEffect(() => {
    setDisplayName(account?.display_name ?? "");
    setHandle(account?.handle ?? "");
  }, [account]);

  useEffect(() => () => {
    if (avatarPreview) URL.revokeObjectURL(avatarPreview);
  }, [avatarPreview]);

  useEffect(() => {
    if (!account) {
      setSessions([]);
      return;
    }
    let cancelled = false;
    setSessionsLoading(true);
    void listSessions().then((items) => {
      if (!cancelled) setSessions(items);
    }).catch((caught: unknown) => {
      if (!cancelled) setError(authErrorMessage(caught, errorCopy[locale]));
    }).finally(() => {
      if (!cancelled) setSessionsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [account, listSessions, locale]);

  async function onProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!account) return;
    const payload: { display_name?: string; handle?: string } = {};
    if (displayName.trim() !== (account.display_name ?? "")) payload.display_name = displayName.trim();
    if (handle.trim() !== account.handle) payload.handle = handle.trim();
    if (Object.keys(payload).length === 0) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await updateProfile(payload);
      setSuccess(copy.saved);
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setSaving(false);
    }
  }

  function onAvatarChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    setError(null);
    setSuccess(null);
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setError(copy.invalidAvatar);
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setError(copy.avatarTooLarge);
      return;
    }
    setAvatarFile(file);
    setAvatarPreview((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : null;
    });
  }

  async function onAvatarSave() {
    if (!avatarFile) return;
    setAvatarBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await replaceAvatar(avatarFile);
      setAvatarFile(null);
      setAvatarPreview((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return null;
      });
      setSuccess(copy.avatarSaved);
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setAvatarBusy(false);
    }
  }

  async function onAvatarDelete() {
    setAvatarBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await deleteAvatar();
      setAvatarFile(null);
      setAvatarPreview((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return null;
      });
      setSuccess(copy.avatarRemoved);
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setAvatarBusy(false);
    }
  }

  async function onRevoke(session: CommunityDeviceSession) {
    setRevokingId(session.id);
    setError(null);
    try {
      await revokeSession(session.id);
      if (!session.current) setSessions((items) => items.filter((item) => item.id !== session.id));
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setRevokingId(null);
    }
  }

  async function onLogout() {
    setSigningOut(true);
    setError(null);
    try {
      await logout();
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale]));
    } finally {
      setSigningOut(false);
    }
  }

  if (status === "booting") return <LoadingState label={copy.loading} />;

  if (!account) {
    return <div className="community-page-stack"><div className="community-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.signedOut} tone="neutral" /></div>{bootstrapError ? <FormNotice>{copy.accountUnavailable}</FormNotice> : null}<Panel className="account-connect-panel"><div className="account-connect-mark"><LogIn size={22} /></div><div><h3>{copy.signedOut}</h3><p>{copy.signedOutDetail}</p><div className="account-benefits">{copy.benefits.map((benefit) => <span key={benefit}><Check size={14} />{benefit}</span>)}</div></div><div className="account-entry-actions"><LinkButton href={communityAuthRoutePaths.login} icon={LogIn} variant="primary">{copy.login}</LinkButton><LinkButton href={communityAuthRoutePaths.register} icon={UserPlus}>{copy.register}</LinkButton></div></Panel><Panel><SectionHeading eyebrow={copy.boundary} title={copy.public} detail={copy.boundaryDetail} action={<ShieldCheck size={18} />} /></Panel></div>;
  }

  const avatarSource = avatarPreview ?? account.avatar_url ?? null;
  return <div className="community-page-stack"><div className="community-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.connected} tone="good" /></div>{error ? <FormNotice>{error}</FormNotice> : null}{success ? <FormNotice tone="success">{success}</FormNotice> : null}<div className="account-settings-grid"><Panel><SectionHeading eyebrow={copy.profile} title={account.display_name || account.handle} detail={copy.profileDetail} action={<KeyRound size={18} />} /><form className="account-profile-form" onSubmit={onProfileSubmit}><div className="account-avatar-editor"><div className="account-avatar-preview">{avatarSource ? <img src={avatarSource} alt={copy.avatarPreview} /> : <span>{(account.display_name || account.handle).slice(0, 2).toUpperCase()}</span>}</div><div className="account-avatar-copy"><strong>{copy.avatar}</strong><small>{copy.avatarDetail}</small><input ref={avatarInputRef} className="account-avatar-input" type="file" accept="image/png,image/jpeg,image/webp" aria-label={copy.chooseAvatar} onChange={onAvatarChange} /><div className="account-avatar-actions"><Button type="button" icon={ImagePlus} onClick={() => avatarInputRef.current?.click()}>{avatarSource ? copy.replaceAvatar : copy.chooseAvatar}</Button>{avatarFile ? <Button type="button" variant="primary" icon={avatarBusy ? LoaderCircle : Save} disabled={avatarBusy} onClick={() => void onAvatarSave()}>{avatarBusy ? copy.saving : copy.save}</Button> : null}{account.avatar_url && !avatarFile ? <Button type="button" variant="danger" icon={avatarBusy ? LoaderCircle : Trash2} disabled={avatarBusy} onClick={() => void onAvatarDelete()}>{avatarBusy ? copy.removingAvatar : copy.removeAvatar}</Button> : null}</div></div></div><FormField label={copy.name}><input autoComplete="name" maxLength={80} required value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></FormField><FormField label={copy.handle} hint={copy.handleHint}><input autoCapitalize="none" autoCorrect="off" maxLength={32} pattern="[a-z0-9][a-z0-9-]{1,30}[a-z0-9]" required spellCheck={false} value={handle} onChange={(event) => setHandle(event.target.value.toLowerCase())} /></FormField><FormField label={copy.email}><input disabled readOnly type="email" value={account.email} /></FormField><Button type="submit" variant="primary" disabled={saving || (displayName.trim() === (account.display_name ?? "") && handle.trim() === account.handle)} icon={saving ? LoaderCircle : Save}>{saving ? copy.saving : copy.save}</Button></form></Panel><Panel><SectionHeading eyebrow={copy.devices} title={copy.devices} detail={copy.devicesDetail} action={<MonitorSmartphone size={18} />} />{sessionsLoading ? <LoadingState label={copy.loading} /> : <div className="session-list">{sessions.map((session) => <article className="session-item" key={session.id}><span className="session-icon"><MonitorSmartphone size={18} /></span><div><strong>{session.device_name || session.user_agent}</strong>{session.current ? <StatusBadge label={copy.current} tone="good" /> : null}<small>{copy.lastActive}: {formatDate(session.last_seen_at, locale)}</small><small>{copy.expires}: {formatDate(session.expires_at, locale)}</small></div><Button size="sm" variant={session.current ? "danger" : "secondary"} disabled={revokingId === session.id} onClick={() => void onRevoke(session)}>{revokingId === session.id ? copy.revoking : copy.revoke}</Button></article>)}{sessions.length === 0 ? <p className="session-empty">{copy.noSessions}</p> : null}</div>}<Button className="account-signout-button" variant="danger" icon={signingOut ? LoaderCircle : LogOut} disabled={signingOut} onClick={() => void onLogout()}>{signingOut ? copy.signingOut : copy.signOut}</Button></Panel></div></div>;
}
