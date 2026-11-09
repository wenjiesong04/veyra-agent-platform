import { useEffect, useState } from "react";
import { Check, KeyRound, Moon, Palette, Plug, Server, Settings2, Sun } from "lucide-react";
import type { FactoryStatus, SecretStatus } from "@veyra/api-contracts";
import { Button, StatusBadge, useLocale, useTheme, type ThemeChoice } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";
import { FactoryCapabilitySummary } from "../features/settings/factory-capability-summary";
import { ProviderCredentialsPanel } from "../features/settings/provider-credentials-panel";
import { ModelRegistryPanel } from "../features/settings/model-registry-panel";

const choices: Array<{ value: ThemeChoice; icon: typeof Sun }> = [
  { value: "system", icon: Settings2 },
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
];

export function SettingsPage() {
  const { locale, language, setLanguage } = useLocale();
  const { theme, setTheme, motion, setMotion } = useTheme();
  const { api } = useProjectWorkspace();
  const initialQuery = new URLSearchParams(window.location.hash.split("?")[1] ?? "");
  const [section, setSection] = useState<"models" | "appearance" | "integrations" | "services">((initialQuery.get("settingsSection") === "appearance" || initialQuery.get("settingsSection") === "integrations" || initialQuery.get("settingsSection") === "services") ? initialQuery.get("settingsSection") as "appearance" | "integrations" | "services" : "models");
  const [credentialId, setCredentialId] = useState<string | null>(initialQuery.get("providerId"));
  function selectSection(next: "models" | "appearance" | "integrations" | "services") {
    setSection(next);
    const query = new URLSearchParams(window.location.hash.split("?")[1] ?? "");
    if (next === "models") query.delete("settingsSection"); else query.set("settingsSection", next);
    window.history.replaceState(null, "", `#/settings${query.size ? `?${query}` : ""}`);
  }
  function selectCredential(id: string | null) {
    setCredentialId(id);
    const query = new URLSearchParams(window.location.hash.split("?")[1] ?? "");
    if (id) query.set("providerId", id); else query.delete("providerId");
    query.delete("action");
    query.delete("modelProfileId");
    window.history.replaceState(null, "", `#/settings${query.size ? `?${query}` : ""}`);
  }
  const [githubToken, setGithubToken] = useState("");
  const [githubStatus, setGithubStatus] = useState<SecretStatus | null>(null);
  const [githubMessage, setGithubMessage] = useState("");
  const [githubBusy, setGithubBusy] = useState(false);
  const [factoryStatus, setFactoryStatus] = useState<FactoryStatus | null>(null);
  const [factoryBusy, setFactoryBusy] = useState(false);
  const [factoryMessage, setFactoryMessage] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const copy = locale === "zh" ? {
    title: "账号与模型", appearance: "界面偏好", theme: "主题", themeDetail: "选择白昼、暗夜或跟随系统。",
    system: "系统", light: "白昼", dark: "暗夜", githubToken: "GitHub 访问密钥",
    githubDetail: "连接代码仓库时使用。普通模型任务无需配置。",
    token: "访问密钥", save: "保存密钥", clear: "清除密钥", loading: "读取中…",
    configured: "已配置", missing: "未配置", keychain: "系统安全凭据库", environment: "环境变量回退",
    savedSecret: "Token 已安全保存到本机。", clearedSecret: "本机保存的 Token 已清除。",
    secretUnavailable: "当前本机服务不支持凭据管理。", secretFailed: "凭据操作失败，请检查本机服务后重试。",
  } : {
    title: "Account & model access", appearance: "Appearance", theme: "Theme", themeDetail: "Choose light, dark or system appearance.",
    system: "System", light: "Light", dark: "Dark", githubToken: "GitHub Token",
    githubDetail: "Stored securely on this device for authorized GitHub tools.",
    token: "Token", save: "Save Token", clear: "Clear Token", loading: "Loading…",
    configured: "Configured", missing: "Not configured", keychain: "System credential store", environment: "Environment fallback",
    savedSecret: "Token saved securely on this device.", clearedSecret: "The locally saved Token was cleared.",
    secretUnavailable: "The local service does not support credential management.", secretFailed: "Credential operation failed. Check the local service and retry.",
  };
  const labels: Record<ThemeChoice, string> = { system: copy.system, light: copy.light, dark: copy.dark };

  useEffect(() => {
    let active = true;
    if (!api.getSecretStatus) {
      setGithubMessage(copy.secretUnavailable);
      return () => { active = false; };
    }
    void api.getSecretStatus("github.main").then((status) => {
      if (active) setGithubStatus(status);
    }).catch(() => {
      if (active) setGithubMessage(copy.secretFailed);
    });
    return () => { active = false; };
  }, [api, copy.secretFailed, copy.secretUnavailable]);

  useEffect(() => {
    let active = true;
    if (!api.factoryStatus) { setFactoryMessage(locale === "zh" ? "当前应用未提供创作助手状态。" : "Assistant status is unavailable in this app."); return () => { active = false; }; }
    void api.factoryStatus().then((next) => {
      if (active) { setFactoryStatus(next); setFactoryMessage(""); }
    }).catch(() => { if (active) setFactoryMessage(locale === "zh" ? "暂时无法读取创作助手状态，请检查本机服务后重试。" : "Could not read assistant status. Check the local service and retry."); });
    return () => { active = false; };
  }, [api, locale]);

  async function saveGithubToken() {
    if (!api.setSecret || !githubToken.trim()) return;
    setGithubBusy(true);
    setGithubMessage("");
    try {
      const status = await api.setSecret("github.main", githubToken);
      setGithubStatus(status);
      setGithubToken("");
      setGithubMessage(copy.savedSecret);
    } catch {
      setGithubMessage(copy.secretFailed);
    } finally {
      setGithubBusy(false);
    }
  }

  async function clearGithubToken() {
    if (!api.deleteSecret) return;
    setGithubBusy(true);
    setGithubMessage("");
    try {
      const status = await api.deleteSecret("github.main");
      setGithubStatus(status);
      setConfirmClear(false);
      setGithubMessage(copy.clearedSecret);
    } catch {
      setGithubMessage(copy.secretFailed);
    } finally {
      setGithubBusy(false);
    }
  }

  async function recheckFactory() {
    if (!api.probeFactoryCapabilities) return;
    setFactoryBusy(true);
    setFactoryMessage("");
    try {
      setFactoryStatus(await api.probeFactoryCapabilities());
    } catch {
      setFactoryMessage(locale === "zh" ? "平台服务检查失败，请稍后重试。" : "Platform service check failed. Try again later.");
    } finally {
      setFactoryBusy(false);
    }
  }

  const secretLabel = githubStatus?.source === "keychain"
    ? copy.keychain
    : githubStatus?.source === "environment" ? copy.environment : githubStatus ? copy.missing : copy.loading;
  const secretTone = githubStatus?.configured ? "good" : "warn";
  const sections = [
    { value: "models", label: locale === "zh" ? "我的 API" : "Model APIs", icon: Plug },
    { value: "appearance", label: copy.appearance, icon: Palette },
    { value: "integrations", label: locale === "zh" ? "工具授权" : "Tool credentials", icon: KeyRound },
    { value: "services", label: locale === "zh" ? "创作助手" : "Creation assistant", icon: Server },
  ] as const;
  return <div className="settings-page">
    <aside className="settings-navigation"><h2>{locale === "zh" ? "设置" : "Settings"}</h2>
      <nav className="settings-sections" aria-label={locale === "zh" ? "设置分类" : "Settings sections"}>
        {sections.map(({ value, label, icon: Icon }) => <button key={value} type="button" aria-pressed={section === value} onClick={() => selectSection(value)}><Icon size={17} aria-hidden="true" /><span>{label}</span></button>)}
      </nav>
    </aside>
    <div className="settings-content">
      {section === "models" ? <ProviderCredentialsPanel locale={locale} selectedCredentialId={credentialId} onSelectCredential={selectCredential} renderModels={(id, onEdit) => <ModelRegistryPanel locale={locale} credentialId={id} onEditConnection={onEdit} embedded />} />
      : section === "appearance" ? <>
        <header className="settings-content-header"><div><h2>{copy.appearance}</h2><p>{locale === "zh" ? "让工作区适合你的使用习惯。" : "Make the workspace comfortable for you."}</p></div></header>
        <section className="settings-setting-row theme-setting-row"><div className="settings-row-label"><h3>{copy.theme}</h3><p>{copy.themeDetail}</p></div>
          <div className="settings-theme-options">{choices.map(({ value, icon: Icon }) => <button className={`settings-theme-option ${theme === value ? "is-selected" : ""}`} key={value} type="button" aria-pressed={theme === value} onClick={() => setTheme(value)}>
            <span className="settings-theme-preview" data-preview={value} aria-hidden="true"><span className="theme-preview-sidebar"><i /><i /><i /></span><span className="theme-preview-workspace"><i /><span><i /><i /></span></span></span>
            <span className="settings-theme-label"><Icon size={15} aria-hidden="true" /><span>{labels[value]}</span>{theme === value ? <Check size={14} aria-hidden="true" /> : null}</span>
          </button>)}</div>
        </section>
        <section className="settings-setting-row"><div className="settings-row-label"><h3>{locale === "zh" ? "界面动画" : "Interface motion"}</h3><p>{locale === "zh" ? "对动态效果敏感时，可以减少动画。" : "Reduce animations if you are sensitive to motion."}</p></div><div className="settings-row-control"><label className="settings-field"><span className="settings-visually-hidden">{locale === "zh" ? "界面动画" : "Interface motion"}</span><select name="motion-preference" value={motion} onChange={(event) => setMotion(event.target.value as "system" | "reduced")}><option value="system">{locale === "zh" ? "跟随系统设置" : "Follow system settings"}</option><option value="reduced">{locale === "zh" ? "减少动画" : "Reduce animations"}</option></select></label><p className="settings-note" role="status">{motion === "reduced" ? (locale === "zh" ? "已减少界面动画，偏好保存在本机。" : "Interface animations reduced. This preference is saved locally.") : (locale === "zh" ? "自动使用系统的动画偏好。" : "Automatically use your system motion preference.")}</p></div></section>
        <section className="settings-setting-row"><div className="settings-row-label"><h3>{locale === "zh" ? "界面语言" : "Interface language"}</h3><p>{locale === "zh" ? "选择菜单和提示使用的语言。" : "Choose the language for menus and guidance."}</p></div><div className="settings-row-control"><label className="settings-field"><span className="settings-visually-hidden">{locale === "zh" ? "界面语言" : "Interface language"}</span><select name="language-preference" value={language} onChange={(event) => setLanguage(event.target.value as "system" | "zh" | "en")}><option value="system">{locale === "zh" ? "跟随系统设置" : "Follow system settings"}</option><option value="zh">简体中文</option><option value="en">English</option></select></label></div></section>
      </> : section === "integrations" ? <>
        <header className="settings-content-header"><div><h2>{locale === "zh" ? "工具授权" : "Tool credentials"}</h2><p>{locale === "zh" ? "为 Agent 使用的外部工具提供授权。" : "Provide credentials for your Agents' external tools."}</p></div></header>
        <section className="settings-setting-row"><div className="settings-row-label"><h3>{copy.githubToken}</h3><p>{copy.githubDetail}</p><StatusBadge label={githubStatus?.configured ? copy.configured : copy.missing} tone={secretTone} /></div>
          <div className="settings-row-control"><form className="settings-secret-form" onSubmit={(event) => { event.preventDefault(); void saveGithubToken(); }}><label><span>{copy.token}</span><input name="github-token" disabled={githubBusy} type="password" autoComplete="new-password" value={githubToken} onChange={(event) => setGithubToken(event.target.value)} placeholder="ghp_…" /></label>
            <div className="button-row"><Button type="submit" size="sm" variant="primary" disabled={githubBusy || !githubToken.trim() || !api.setSecret}>{githubBusy ? (locale === "zh" ? "保存中…" : "Saving…") : copy.save}</Button><Button size="sm" variant="ghost" disabled={githubBusy || !githubStatus?.configured || !api.deleteSecret} onClick={() => setConfirmClear(true)}>{copy.clear}</Button></div>
          </form>
          {confirmClear ? <div className="runtime-delete-confirm" role="alert"><p>{locale === "zh" ? "清除本机保存的 GitHub Token？相关工具将需要重新配置。" : "Clear the saved GitHub Token? Related tools will need setup again."}</p><div className="button-row"><Button size="sm" disabled={githubBusy} onClick={() => setConfirmClear(false)}>{locale === "zh" ? "取消" : "Cancel"}</Button><Button size="sm" variant="danger" disabled={githubBusy} onClick={() => void clearGithubToken()}>{locale === "zh" ? "确认清除" : "Clear saved Token"}</Button></div></div> : null}
          {githubStatus?.configured ? <p className="settings-note">{secretLabel}</p> : null}{githubMessage ? <p className="settings-secret-message" role="status">{githubMessage}</p> : null}
          </div>
        </section>
      </> : <>
        <header className="settings-content-header"><div><h2>{locale === "zh" ? "创作助手" : "Creation assistant"}</h2><p>{locale === "zh" ? "帮助你把想法变成 Agent 和工作流。" : "Turn your ideas into Agents and Workflows."}</p></div></header>
        {!factoryMessage ? <FactoryCapabilitySummary status={factoryStatus} locale={locale} busy={factoryBusy} onRecheck={() => void recheckFactory()} /> : null}{factoryMessage ? <div className="settings-feedback is-error" role="alert"><p>{factoryMessage}</p><Button size="sm" disabled={factoryBusy || !api.factoryStatus} onClick={() => { setFactoryBusy(true); void api.factoryStatus?.().then((next) => { setFactoryStatus(next); setFactoryMessage(""); }).catch(() => undefined).finally(() => setFactoryBusy(false)); }}>{locale === "zh" ? "重试" : "Retry"}</Button></div> : null}
      </>}
    </div>
  </div>;
}
