import { ArrowUpRight, AtSign, Bookmark, Check, HardDrive, ImagePlus, LoaderCircle, LockKeyhole, LogIn, LogOut, Mail, MonitorSmartphone, PackageCheck, Save, ShieldCheck, Trash2, Upload, UserPlus, UserRound } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { communityAuthRoutePaths, communityRoutePaths, type CommunityDeviceSession } from "@veyra/api-contracts";
import { Button, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, toast, useLocale } from "@veyra/ui";
import { useAuth } from "../auth-context";
import { FormField, FormNotice, authErrorMessage, errorCopy } from "../form-controls";

const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

function formatDate(value: string, locale: "zh" | "en"): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function devicePresentation(session: CommunityDeviceSession, locale: "zh" | "en"): { name: string; detail: string } {
  const agent = session.user_agent;
  const platform = /iPhone/i.test(agent)
    ? "iPhone"
    : /iPad/i.test(agent)
      ? "iPad"
      : /Android/i.test(agent)
        ? "Android"
        : /Windows/i.test(agent)
          ? "Windows"
          : /Macintosh|Mac OS X/i.test(agent)
            ? "Mac"
            : /Linux/i.test(agent)
              ? "Linux"
              : (locale === "zh" ? "未知设备" : "Unknown device");
  const browser = /Edg\//i.test(agent)
    ? "Edge"
    : /Firefox\//i.test(agent)
      ? "Firefox"
      : /Chrome\//i.test(agent)
        ? "Chrome"
        : /Safari\//i.test(agent)
          ? "Safari"
          : (locale === "zh" ? "浏览器会话" : "Browser session");
  const rawName = session.device_name?.trim() ?? "";
  const usableName = rawName && rawName.length <= 56 && !/Mozilla\/|AppleWebKit|Chrome\/|Safari\//i.test(rawName);
  return usableName
    ? { name: rawName, detail: `${platform} · ${browser}` }
    : { name: `${platform} · ${browser}`, detail: locale === "zh" ? "Veyra 登录会话" : "Veyra sign-in session" };
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
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const copy = locale === "zh" ? {
    eyebrow: "账号", title: "你的 Veyra 身份", description: "管理公开资料与登录安全。Project、Agent 和运行数据仍保留在你的本机。", connected: "账号已连接", loading: "正在读取账号", signedOut: "尚未登录", signedOutDetail: "无需账号也可以浏览社区。登录后可以管理个人资料、设备和发布身份。", login: "登录", register: "创建账号", benefits: ["发布不可变版本", "保存与评审条目", "保留 Fork 来源关系"], boundary: "安全边界", public: "公共身份，本机执行", boundaryDetail: "Community 只保存账号和发布元数据，不会执行你的 Agent，也不会读取本地 Project。", profile: "公开资料", profileDetail: "这些信息会出现在创作者页面和你发布的资源旁。", name: "显示名称", handle: "公开标识", handleHint: "3–32 位小写字母、数字或连字符", email: "登录邮箱", emailHint: "邮箱仅用于登录和账号安全，不会显示在社区中。", save: "保存资料", saving: "正在保存", saved: "个人资料已更新。", avatar: "个人头像", avatarDetail: "PNG、JPEG 或 WebP，最大 2 MiB。只保存到 Community 账号。", chooseAvatar: "选择头像", replaceAvatar: "替换头像", removeAvatar: "删除头像", removingAvatar: "正在删除", avatarPreview: "头像预览", devices: "设备记录", devicesDetail: "查看已登录的设备，并撤销不再使用的会话。", session: "个活动会话", sessions: "个活动会话", current: "当前设备", lastActive: "最后活动", expires: "到期", revoke: "撤销访问", revokeCurrent: "退出此设备", revoking: "正在撤销", noSessions: "没有可显示的登录设备。", access: "账号访问", accessDetail: "退出只会结束当前登录，不会删除本地 Project 或 Community 发布记录。", signOut: "退出当前账号", signingOut: "正在退出", accountUnavailable: "暂时无法检查登录状态。你仍然可以浏览社区。", avatarSaved: "头像已更新。", avatarRemoved: "头像已删除。", invalidAvatar: "请选择 PNG、JPEG 或 WebP 图片。", avatarTooLarge: "头像文件不能超过 2 MiB。",
  } : {
    eyebrow: "Account", title: "Your Veyra identity", description: "Manage your public profile and sign-in security. Projects, Agents, and run data stay on your device.", connected: "Account connected", loading: "Loading account", signedOut: "You are not signed in", signedOutDetail: "You can browse Community without an account. Sign in to manage your profile, devices, and publishing identity.", login: "Sign in", register: "Create account", benefits: ["Publish immutable versions", "Save and review entries", "Keep Fork lineage"], boundary: "Security boundary", public: "Public identity, local execution", boundaryDetail: "Community stores account and publication metadata only. It cannot execute your Agents or read local Projects.", profile: "Public profile", profileDetail: "This information appears on your creator page and beside published resources.", name: "Display name", handle: "Public handle", handleHint: "3–32 lowercase letters, numbers, or hyphens", email: "Sign-in email", emailHint: "Used for sign-in and account security. It is never shown in Community.", save: "Save profile", saving: "Saving", saved: "Profile updated.", avatar: "Profile image", avatarDetail: "PNG, JPEG, or WebP up to 2 MiB. Stored only with your Community account.", chooseAvatar: "Choose avatar", replaceAvatar: "Replace avatar", removeAvatar: "Remove avatar", removingAvatar: "Removing", avatarPreview: "Avatar preview", devices: "Device records", devicesDetail: "Review signed-in devices and revoke sessions you no longer use.", session: "active session", sessions: "active sessions", current: "Current device", lastActive: "Last active", expires: "Expires", revoke: "Revoke access", revokeCurrent: "Sign out this device", revoking: "Revoking", noSessions: "There are no sign-in devices to display.", access: "Account access", accessDetail: "Signing out ends this session only. Local Projects and Community releases are not deleted.", signOut: "Sign out of this account", signingOut: "Signing out", accountUnavailable: "We could not check your sign-in state. You can still browse Community.", avatarSaved: "Avatar updated.", avatarRemoved: "Avatar removed.", invalidAvatar: "Choose a PNG, JPEG, or WebP image.", avatarTooLarge: "Avatar files must be 2 MiB or smaller.",
  };
  const accountContent = locale === "zh" ? {
    community: "Community 中的你",
    communityDetail: "使用这个身份发布、收藏和复用有版本记录的社区资源。",
    creator: "创作者工作台",
    creatorDetail: "准备发布并查看审核与反馈",
    releases: "已发布版本",
    releasesDetail: "查看公开、审核中和被拒绝的版本",
    saved: "已收藏资源",
    savedDetail: "回到你保存的不可变版本",
    enabled: "当前账号已启用",
    local: "这些内容留在本机",
    localDetail: "登录不会上传或按账号分割本地工作空间。只有你明确发布或同步的内容才会离开设备。",
    localItems: ["Project、Agent 与 Workflow 源文件", "Run 历史、审批和执行回执", "Secret 值与本机凭据"],
  } : {
    community: "Your Community identity",
    communityDetail: "Use this identity to publish, save, and reuse versioned Community resources.",
    creator: "Creator workspace",
    creatorDetail: "Prepare releases and review moderation or feedback",
    releases: "Published releases",
    releasesDetail: "Review public, pending, and rejected versions",
    saved: "Saved resources",
    savedDetail: "Return to immutable releases you have starred",
    enabled: "Enabled for this account",
    local: "What stays on this device",
    localDetail: "Signing in does not upload or partition local workspaces by account. Content leaves the device only when you explicitly publish or sync it.",
    localItems: ["Project, Agent, and Workflow source files", "Run history, approvals, and execution receipts", "Secret values and host credentials"],
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
      if (!cancelled) setError(authErrorMessage(caught, errorCopy[locale], "account"));
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
    try {
      await updateProfile(payload);
      toast.success(copy.saved);
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale], "account"));
    } finally {
      setSaving(false);
    }
  }

  function onAvatarChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    setError(null);
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
    try {
      await replaceAvatar(avatarFile);
      setAvatarFile(null);
      setAvatarPreview((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return null;
      });
      toast.success(copy.avatarSaved);
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale], "account"));
    } finally {
      setAvatarBusy(false);
    }
  }

  async function onAvatarDelete() {
    setAvatarBusy(true);
    setError(null);
    try {
      await deleteAvatar();
      setAvatarFile(null);
      setAvatarPreview((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return null;
      });
      toast.success(copy.avatarRemoved);
    } catch (caught) {
      setError(authErrorMessage(caught, errorCopy[locale], "account"));
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
      setError(authErrorMessage(caught, errorCopy[locale], "account"));
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
      setError(authErrorMessage(caught, errorCopy[locale], "account"));
    } finally {
      setSigningOut(false);
    }
  }

  if (status === "booting") return <LoadingState label={copy.loading} />;

  if (!account) {
    return <div className="community-page-stack"><div className="community-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.signedOut} tone="neutral" /></div>{bootstrapError ? <FormNotice>{copy.accountUnavailable}</FormNotice> : null}<Panel className="account-connect-panel"><div className="account-connect-mark"><LogIn size={22} /></div><div><h3>{copy.signedOut}</h3><p>{copy.signedOutDetail}</p><div className="account-benefits">{copy.benefits.map((benefit) => <span key={benefit}><Check size={14} />{benefit}</span>)}</div></div><div className="account-entry-actions"><LinkButton href={communityAuthRoutePaths.login} icon={LogIn} variant="primary">{copy.login}</LinkButton><LinkButton href={communityAuthRoutePaths.register} icon={UserPlus}>{copy.register}</LinkButton></div></Panel><Panel><SectionHeading eyebrow={copy.boundary} title={copy.public} detail={copy.boundaryDetail} action={<ShieldCheck size={18} />} /></Panel></div>;
  }

  const avatarSource = avatarPreview ?? account.avatar_url ?? null;
  return (
    <div className="community-page-stack account-page">
      <header className="account-identity-hero">
        <div className={`account-hero-avatar${avatarSource ? " has-photo" : ""}`}>
          {avatarSource ? <img src={avatarSource} alt="" /> : <span>{(account.display_name || account.handle).slice(0, 2).toUpperCase()}</span>}
        </div>
        <div className="account-identity-copy">
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <div className="account-title-row"><h1>{account.display_name || account.handle}</h1></div>
          <div className="account-identity-meta"><span><AtSign size={13} aria-hidden="true" />{account.handle}</span><span><Mail size={13} aria-hidden="true" />{account.email}</span></div>
          <p>{copy.description}</p>
        </div>
        <div className="account-boundary-note is-connected" role="status">
          <i aria-hidden="true" />
          <strong>{copy.connected}</strong>
        </div>
      </header>

      {error ? <FormNotice>{error}</FormNotice> : null}

      <div className="account-workspace">
        <div className="account-primary-column">
          <Panel className="account-profile-panel">
          <div className="account-section-heading">
            <span className="account-section-icon"><UserRound size={18} aria-hidden="true" /></span>
            <div><h2>{copy.profile}</h2><p>{copy.profileDetail}</p></div>
          </div>
          <form className="account-profile-form" onSubmit={onProfileSubmit}>
            <div className="account-avatar-editor">
              <div className={`account-avatar-preview${avatarSource ? " has-photo" : ""}`}>{avatarSource ? <img src={avatarSource} alt={copy.avatarPreview} /> : <span>{(account.display_name || account.handle).slice(0, 2).toUpperCase()}</span>}</div>
              <div className="account-avatar-copy">
                <strong>{copy.avatar}</strong>
                <small>{copy.avatarDetail}</small>
                <input ref={avatarInputRef} className="account-avatar-input" type="file" accept="image/png,image/jpeg,image/webp" aria-label={copy.chooseAvatar} onChange={onAvatarChange} />
                <div className="account-avatar-actions">
                  <Button type="button" icon={ImagePlus} onClick={() => avatarInputRef.current?.click()}>{avatarSource ? copy.replaceAvatar : copy.chooseAvatar}</Button>
                  {avatarFile ? <Button type="button" variant="primary" icon={avatarBusy ? LoaderCircle : Save} disabled={avatarBusy} onClick={() => void onAvatarSave()}>{avatarBusy ? copy.saving : copy.save}</Button> : null}
                  {account.avatar_url && !avatarFile ? <Button type="button" variant="danger" icon={avatarBusy ? LoaderCircle : Trash2} disabled={avatarBusy} onClick={() => void onAvatarDelete()}>{avatarBusy ? copy.removingAvatar : copy.removeAvatar}</Button> : null}
                </div>
              </div>
            </div>
            <div className="account-fields-grid">
              <FormField label={copy.name}><input autoComplete="name" maxLength={80} required value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></FormField>
              <FormField label={copy.handle} hint={copy.handleHint}><input autoCapitalize="none" autoCorrect="off" maxLength={32} pattern="[a-z0-9][a-z0-9-]{1,30}[a-z0-9]" required spellCheck={false} value={handle} onChange={(event) => setHandle(event.target.value.toLowerCase())} /></FormField>
              <div className="account-email-field"><FormField label={copy.email} hint={copy.emailHint}><input disabled readOnly type="email" value={account.email} /></FormField></div>
            </div>
            <div className="account-form-footer">
              <span>{locale === "zh" ? "修改后需要手动保存。" : "Changes are saved only when you confirm."}</span>
              <Button type="submit" variant="primary" disabled={saving || (displayName.trim() === (account.display_name ?? "") && handle.trim() === account.handle)} icon={saving ? LoaderCircle : Save}>{saving ? copy.saving : copy.save}</Button>
            </div>
          </form>
          </Panel>

          <Panel className="account-community-panel">
            <div className="account-section-heading">
              <span className="account-section-icon"><Upload size={18} aria-hidden="true" /></span>
              <div><h2>{accountContent.community}</h2><p>{accountContent.communityDetail}</p></div>
            </div>
            <nav className="account-community-links" aria-label={accountContent.community}>
              <a href={communityRoutePaths.mine}><span className="account-community-link-icon"><Upload size={16} aria-hidden="true" /></span><span><strong>{accountContent.creator}</strong><small>{accountContent.creatorDetail}</small></span><ArrowUpRight size={15} aria-hidden="true" /></a>
              <a href={communityRoutePaths.published}><span className="account-community-link-icon"><PackageCheck size={16} aria-hidden="true" /></span><span><strong>{accountContent.releases}</strong><small>{accountContent.releasesDetail}</small></span><ArrowUpRight size={15} aria-hidden="true" /></a>
              <a href={communityRoutePaths.starred}><span className="account-community-link-icon"><Bookmark size={16} aria-hidden="true" /></span><span><strong>{accountContent.saved}</strong><small>{accountContent.savedDetail}</small></span><ArrowUpRight size={15} aria-hidden="true" /></a>
            </nav>
            <div className="account-community-capabilities">
              <span>{accountContent.enabled}</span>
              <div>{copy.benefits.map((benefit) => <em key={benefit}><Check size={12} aria-hidden="true" />{benefit}</em>)}</div>
            </div>
            <div className="account-local-boundary">
              <span className="account-local-boundary-icon"><HardDrive size={17} aria-hidden="true" /></span>
              <div><strong>{accountContent.local}</strong><p>{accountContent.localDetail}</p><ul>{accountContent.localItems.map((item) => <li key={item}><LockKeyhole size={12} aria-hidden="true" />{item}</li>)}</ul></div>
            </div>
          </Panel>
        </div>

        <aside className="account-security-column">
          <Panel className="account-security-panel">
            <div className="account-section-heading">
              <span className="account-section-icon"><MonitorSmartphone size={18} aria-hidden="true" /></span>
              <div><div className="account-section-title-row"><h2>{copy.devices}</h2>{!sessionsLoading ? <span>{sessions.length} {sessions.length === 1 ? copy.session : copy.sessions}</span> : null}</div><p>{copy.devicesDetail}</p></div>
            </div>
            {sessionsLoading ? <LoadingState label={copy.loading} /> : <div className="session-list">{sessions.map((session) => {
              const device = devicePresentation(session, locale);
              return <article className={`session-item${session.current ? " is-current" : ""}`} key={session.id}>
                <span className="session-icon"><MonitorSmartphone size={17} aria-hidden="true" /></span>
                <div className="session-copy">
                  <div className="session-name-row"><strong>{device.name}</strong>{session.current ? <StatusBadge label={copy.current} tone="good" /> : null}</div>
                  <span className="session-device-detail">{device.detail}</span>
                  <div className="session-dates"><small>{copy.lastActive}: {formatDate(session.last_seen_at, locale)}</small><small>{copy.expires}: {formatDate(session.expires_at, locale)}</small></div>
                </div>
                <Button size="sm" variant={session.current ? "danger" : "secondary"} disabled={revokingId === session.id} onClick={() => void onRevoke(session)}>{revokingId === session.id ? copy.revoking : session.current ? copy.revokeCurrent : copy.revoke}</Button>
              </article>;
            })}{sessions.length === 0 ? <p className="session-empty">{copy.noSessions}</p> : null}</div>}
          </Panel>

          <section className="account-access-card">
            <div><strong>{copy.access}</strong><p>{copy.accessDetail}</p></div>
            <Button className="account-signout-button" variant="danger" icon={signingOut ? LoaderCircle : LogOut} disabled={signingOut} onClick={() => void onLogout()}>{signingOut ? copy.signingOut : copy.signOut}</Button>
          </section>
        </aside>
      </div>
    </div>
  );
}
