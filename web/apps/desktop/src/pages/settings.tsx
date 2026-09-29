import { useEffect, useState } from "react";
import { Check, KeyRound, Moon, Palette, Settings2, Sun } from "lucide-react";
import type { FactoryStatus, SecretStatus } from "@veyra/api-contracts";
import { Button, Panel, SectionHeading, StatusBadge, useLocale, useTheme, type ThemeChoice } from "@veyra/ui";
import { useProjectWorkspace } from "../api/project-workspace";
import { FactoryCapabilitySummary } from "../features/settings/factory-capability-summary";
import { ProviderCredentialsPanel } from "../features/settings/provider-credentials-panel";

const choices: Array<{ value: ThemeChoice; icon: typeof Sun }> = [
  { value: "system", icon: Settings2 },
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
];

export function SettingsPage() {
  const { locale } = useLocale();
  const { theme, setTheme } = useTheme();
  const { api } = useProjectWorkspace();
  const [githubToken, setGithubToken] = useState("");
  const [githubStatus, setGithubStatus] = useState<SecretStatus | null>(null);
  const [githubMessage, setGithubMessage] = useState("");
  const [githubBusy, setGithubBusy] = useState(false);
  const [factoryStatus, setFactoryStatus] = useState<FactoryStatus | null>(null);
  const [factoryBusy, setFactoryBusy] = useState(false);
  const copy = locale === "zh" ? {
    eyebrow: "设置", title: "账号与模型", description: "先区分 Veyra 的 Builder 服务和你的 Agent Runtime API，再管理外观与本机凭据。", saved: "已保存到本机", appearance: "外观", theme: "主题", themeDetail: "选择舒适的白昼、暗夜或跟随系统界面。", system: "系统", light: "白昼", dark: "暗夜", workspace: "工作区", boundary: "本机边界", boundaryDetail: "没有远程访问时，桌面壳层仍然可用。", execution: "执行", localOnly: "仅限本机", effects: "外部效果", guarded: "受控", source: "源文件", userOwned: "用户拥有", evidence: "运行证据", replayable: "可重放", storage: "布局偏好是此壳层唯一使用的浏览器存储。", accessibility: "无障碍", comfort: "舒适默认值", comfortDetail: "壳层遵循减少动态效果偏好，并保持焦点状态可见。", reset: "重置布局", change: "侧栏宽度和主题随时可以更改。", secrets: "其它凭据", githubToken: "GitHub Token", githubDetail: "保存到本机 Keychain；GitHub 工具只读取已授权的 github.main 引用。", modelKey: "模型 API Key", modelDetail: "模型 API 已迁移到下方的 Provider Credentials；这里不再保存共享 Runtime Key。", token: "Token", save: "保存 Token", clear: "清除 Keychain", loading: "读取中", configured: "已配置", missing: "未配置", keychain: "macOS Keychain", environment: "环境变量回退", savedSecret: "Token 已保存到本机 Keychain。", clearedSecret: "Keychain 中的 Token 已清除。", secretUnavailable: "当前桌面 sidecar 不支持凭据管理。", secretFailed: "凭据操作失败，请检查 sidecar 状态。",
  } : {
    eyebrow: "Settings", title: "Account & model access", description: "Keep Veyra Builder access separate from your Agent Runtime API, then manage appearance and local credentials.", saved: "Saved locally", appearance: "Appearance", theme: "Theme", themeDetail: "Choose a calm light, dark, or system surface.", system: "System", light: "Light", dark: "Dark", workspace: "Workspace", boundary: "Local boundary", boundaryDetail: "The desktop shell stays useful without remote access.", execution: "Execution", localOnly: "Local only", effects: "External effects", guarded: "Guarded", source: "Source files", userOwned: "User-owned", evidence: "Run evidence", replayable: "Replayable", storage: "Layout preferences are the only browser storage used by this shell.", accessibility: "Accessibility", comfort: "Comfort defaults", comfortDetail: "The shell follows reduced-motion preferences and keeps focus states visible.", reset: "Reset layout", change: "Sidebar width and theme can be changed any time.", secrets: "Other credentials", githubToken: "GitHub Token", githubDetail: "Stored in the local Keychain; GitHub tools only read the approved github.main reference.", modelKey: "Model API Key", modelDetail: "Model API access now lives in Provider Credentials below; this section does not store a shared Runtime key.", token: "Token", save: "Save Token", clear: "Clear Keychain", loading: "Loading", configured: "Configured", missing: "Not configured", keychain: "macOS Keychain", environment: "Environment fallback", savedSecret: "Token saved to the local Keychain.", clearedSecret: "The Keychain Token was cleared.", secretUnavailable: "This desktop sidecar does not support credential management.", secretFailed: "Credential operation failed. Check the sidecar status.",
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
    if (!api.factoryStatus) return () => { active = false; };
    void api.factoryStatus().then((next) => {
      if (active) setFactoryStatus(next);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [api]);

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
    try {
      setFactoryStatus(await api.probeFactoryCapabilities());
    } finally {
      setFactoryBusy(false);
    }
  }

  const secretLabel = githubStatus?.source === "keychain"
    ? copy.keychain
    : githubStatus?.source === "environment" ? copy.environment : githubStatus ? copy.missing : copy.loading;
  const secretTone = githubStatus?.configured ? "good" : "warn";
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.saved} tone="good" /></div><div className="content-grid two-thirds"><Panel><SectionHeading eyebrow={copy.appearance} title={copy.theme} detail={copy.themeDetail} /><div className="choice-list">{choices.map(({ value, icon: Icon }) => <button className={theme === value ? "choice active" : "choice"} key={value} type="button" onClick={() => setTheme(value)}><Icon size={17} /><span>{labels[value]}</span>{theme === value ? <Check size={15} /> : null}</button>)}</div></Panel><Panel><SectionHeading eyebrow={copy.workspace} title={copy.boundary} detail={copy.boundaryDetail} /><div className="settings-facts"><div><span>{copy.execution}</span><strong>{copy.localOnly}</strong></div><div><span>{copy.effects}</span><strong>{copy.guarded}</strong></div><div><span>{copy.source}</span><strong>{copy.userOwned}</strong></div><div><span>{copy.evidence}</span><strong>{copy.replayable}</strong></div></div><div className="settings-note"><Palette size={16} /><span>{copy.storage}</span></div></Panel></div><Panel><SectionHeading eyebrow={copy.secrets} title={copy.githubToken} detail={copy.githubDetail} /><div className="settings-secret-form"><label><span>{copy.token}</span><input type="password" autoComplete="new-password" value={githubToken} onChange={(event) => setGithubToken(event.target.value)} placeholder="ghp_…" /></label><div className="button-row"><Button icon={KeyRound} variant="primary" disabled={githubBusy || !githubToken.trim() || !api.setSecret} onClick={() => void saveGithubToken()}>{copy.save}</Button><Button variant="secondary" disabled={githubBusy || !api.deleteSecret} onClick={() => void clearGithubToken()}>{copy.clear}</Button></div></div><div className="settings-secret-status"><StatusBadge label={githubStatus?.configured ? copy.configured : copy.missing} tone={secretTone} /><span>{secretLabel}</span></div>{githubMessage ? <p className="settings-secret-message" role="status">{githubMessage}</p> : null}</Panel><ProviderCredentialsPanel locale={locale} /><FactoryCapabilitySummary status={factoryStatus} locale={locale} busy={factoryBusy} onRecheck={() => void recheckFactory()} /><Panel><SectionHeading eyebrow={copy.accessibility} title={copy.comfort} detail={copy.comfortDetail} /><div className="accessibility-row"><Button variant="secondary">{copy.reset}</Button><span>{copy.change}</span></div></Panel></div>;
}
