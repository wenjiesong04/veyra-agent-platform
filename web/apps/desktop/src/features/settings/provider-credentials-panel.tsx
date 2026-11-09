import * as React from "react";
import { ChevronDown, KeyRound, LockKeyhole, Plus, Settings2 } from "lucide-react";
import { Button, Panel, StatusBadge } from "@veyra/ui";
import type { ProviderCredential, ProviderCredentialValidationResponse } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../../api/project-workspace";
import { RuntimeProviderSetup } from "../runtime/RuntimeProviderSetup";
import { ProviderConnectionEdit } from "./provider-connection-edit";
import { presetForAddress, serviceAddressIssue } from "../runtime/provider-presets";
import { connectionFailureMessage } from "../runtime/connection-feedback";
import { LocalApiClientError } from "../../api/local-client";
import { SettingsDialog } from "./settings-dialog";
import "../runtime/runtime-setup.css";

const providerLabels: Record<string, string> = { moonshot: "Moonshot", openai: "OpenAI", anthropic: "Anthropic", openrouter: "OpenRouter", openai_compatible: "OpenAI-compatible" };
function statusLabel(item: ProviderCredential, zh: boolean): string {
  if (item.readiness === "ready") return zh ? "已连接" : "Connected";
  if (item.readiness === "needs_reentry") return zh ? "需重新输入密钥" : "Needs Key re-entry";
  if (item.readiness === "unavailable") return zh ? "安全存储不可用" : "Secure store unavailable";
  if (item.readiness === "disabled") return zh ? "已停用" : "Disabled";
  if (item.readiness === "invalid") return zh ? "连接检查失败" : "Connection failed";
  return zh ? "等待检查" : "Unchecked";
}
function formatDate(value: string | null, zh: boolean): string {
  if (!value) return zh ? "尚无记录" : "No record yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(zh ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" });
}

export function ProviderCredentialsPanel({ locale, selectedCredentialId, onSelectCredential, renderModels }: {
  locale: "zh" | "en";
  selectedCredentialId?: string | null;
  onSelectCredential?: (id: string | null) => void;
  renderModels?: (id: string, onEdit: () => void) => React.ReactNode;
}) {
  const { api } = useProjectWorkspace();
  const zh = locale === "zh";
  const query = new URLSearchParams(window.location.hash.split("?")[1] ?? "");
  const [selection, setSelection] = React.useState<string | null>(null);
  const [items, setItems] = React.useState<ProviderCredential[]>([]);
  const [open, setOpen] = React.useState(query.get("action") === "add-provider");
  const [editConnection, setEditConnection] = React.useState<ProviderCredential | null>(null);
  const [replaceId, setReplaceId] = React.useState<string | null>(null);
  const [replacementKey, setReplacementKey] = React.useState("");
  const [deleteId, setDeleteId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [message, setMessage] = React.useState("");
  const [failed, setFailed] = React.useState(false);
  const [loadError, setLoadError] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!api.listRuntimeCredentials) { setLoading(false); return; }
    try { setItems((await api.listRuntimeCredentials()).credentials); setLoadError(false); }
    catch { setLoadError(true); }
    finally { setLoading(false); }
  }, [api]);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    const refresh = () => { void load(); };
    window.addEventListener("veyra-model-registry-updated", refresh);
    return () => window.removeEventListener("veyra-model-registry-updated", refresh);
  }, [load]);

  const update = (credential: ProviderCredential) => {
    setItems((current) => current.some((item) => item.credential_id === credential.credential_id) ? current.map((item) => item.credential_id === credential.credential_id ? credential : item) : [credential, ...current]);
    window.dispatchEvent(new Event("veyra-model-registry-updated"));
  };
  const connectionMessage = (result: ProviderCredentialValidationResponse) => {
    const registeredDefault = result.models?.some((profile) => profile.provider_model_id === result.credential.default_model_id);
    setFailed(!result.valid && result.code !== "runtime_model_discovery_unavailable");
    setMessage(registeredDefault && ["default_model_unavailable", "runtime_model_discovery_unavailable"].includes(result.code)
      ? (zh ? "API 与模型已保存，接着测试能否完成你的任务。" : "Connection and model saved. Verify the capabilities you need next.")
      : result.code === "default_model_unavailable"
      ? (zh ? "API 已保存，但列表里没有你填写的模型。可在下方添加并测试。" : "Connection saved; the saved default model ID was not listed. Add and verify it in the model panel.")
      : result.valid ? (zh ? "API 连接已检查。请选择模型，再测试需要的用途。" : "Connection checked. Select a model to verify its capabilities.")
      : result.code === "runtime_model_discovery_unavailable" ? (zh ? "服务商没有提供模型列表，可复制模型名称后添加并测试。" : "No model list is available. Add a model ID manually to verify it.")
      : (zh ? connectionFailureMessage(result.code, locale) : "Connection check failed. Check the Key, endpoint and Provider status, then retry."));
  };
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setMessage(""); setFailed(false);
    try { await action(); }
    catch (cause) { setFailed(true); setMessage(connectionFailureMessage(cause instanceof LocalApiClientError ? cause.code : "", locale)); }
    finally { setBusy(false); }
  };

  const selected = items.find((item) => item.credential_id === (selectedCredentialId ?? selection)) ?? items.find((item) => item.is_default) ?? items[0];
  const servicePreset = selected ? presetForAddress(selected.base_url) : undefined;
  const addressIssue = selected ? serviceAddressIssue(selected.base_url, locale) : "";
  return <Panel className="runtime-provider-panel" aria-label={zh ? "模型 API" : "Model APIs"}>
    <div className="settings-content-header">
      <div><h2>{zh ? "我的模型 API" : "My model APIs"}</h2><p>{zh ? "添加你从模型平台获取的 API，供 Agent 和工作流执行任务。" : "Add APIs from your model platforms to run Agents and Workflows."}</p></div>
      <Button icon={Plus} variant={items.length ? "secondary" : "primary"} disabled={busy || !api.createRuntimeCredential} onClick={() => setOpen(true)}>{zh ? "添加 API" : "Add Provider"}</Button>
    </div>
    {addressIssue ? <div className="settings-feedback is-error" role="alert"><strong>{zh ? "服务地址需要修正" : "Correct the service address"}</strong><p>{addressIssue}</p><Button size="sm" disabled={busy || !api.updateRuntimeCredential} onClick={() => setEditConnection(selected!)}>{zh ? "修正服务地址" : "Correct service address"}</Button></div> : null}
    {message ? <p className={`settings-feedback ${failed ? "is-error" : ""}`} role={failed ? "alert" : "status"}>{message}</p> : null}
    {loading ? <p role="status" className="settings-note">{zh ? "正在读取连接…" : "Loading connections…"}</p> : loadError ? <div className="settings-feedback is-error" role="alert">{zh ? "无法读取 API 连接。" : "Could not load API connections."}<Button size="sm" onClick={() => void load()}>{zh ? "重试" : "Retry"}</Button></div> : selected ? <>
      <div className="settings-connection-selector">
        <label><span>{zh ? "已添加的 API" : "API connection"}</span><select disabled={busy} name="api-connection" value={selected.credential_id} onChange={(event) => { setSelection(event.target.value); onSelectCredential?.(event.target.value); setMessage(""); }}>
          {items.map((item) => <option key={item.credential_id} value={item.credential_id}>{item.label}</option>)}
        </select></label>
        <StatusBadge label={statusLabel(selected, zh)} tone={selected.readiness === "ready" ? "good" : selected.readiness === "invalid" || selected.readiness === "unavailable" ? "bad" : "warn"} />
        {selected.is_default ? <span className="runtime-default-badge">{zh ? "默认连接" : "Default connection"}</span> : null}
      </div>
      <article className="settings-connection" aria-label={selected.label} key={selected.credential_id}>
        <div className="settings-connection-meta"><span>{(servicePreset?.[locale] ?? (selected.provider_type === "openai_compatible" ? (zh ? "自定义模型服务" : "Custom model service") : providerLabels[selected.provider_type] ?? selected.provider_type))}</span><span>{selected.credential_scope === "device" ? (zh ? "本设备" : "This device") : (zh ? "云端" : "Cloud")}</span><code>{selected.masked_hint}</code></div>
        <details className="runtime-connection-details"><summary><Settings2 size={14} aria-hidden="true" />{zh ? "连接设置" : "Connection settings"}<ChevronDown className="connection-disclosure" size={14} aria-hidden="true" /></summary>
          <dl className="settings-connection-facts"><div><dt>{zh ? "最初选择的模型" : "Saved default model"}</dt><dd translate="no">{selected.default_model_id ?? (zh ? "未设置" : "Not set")}</dd></div><div><dt>{zh ? "最近检查" : "Last checked"}</dt><dd>{formatDate(selected.validated_at, zh)}</dd></div></dl>
          <div className="runtime-credential-actions"><Button size="sm" disabled={busy || !api.updateRuntimeCredential} onClick={() => setEditConnection(selected)}>{zh ? "修改服务地址" : "Edit service address"}</Button>
            <Button size="sm" disabled={busy || Boolean(addressIssue) || !api.validateRuntimeCredential} onClick={() => void run(async () => { const result = await api.validateRuntimeCredential!(selected.credential_id); update(result.credential); connectionMessage(result); })}>{busy ? (zh ? "检查中…" : "Checking…") : (zh ? "检查连接" : "Check connection")}</Button>
            <Button size="sm" disabled={busy || !api.replaceRuntimeCredential} onClick={() => { setReplaceId(selected.credential_id); setReplacementKey(""); }}>{zh ? "替换 Key" : "Replace Key"}</Button>
            <Button size="sm" disabled={busy || !api.setRuntimeCredentialStatus} onClick={() => void run(async () => {
              const result = await api.setRuntimeCredentialStatus!(selected.credential_id, selected.status !== "active"); update(result.credential);
              if (selected.status !== "active" && !["ready", "unverified"].includes(result.credential.readiness)) {
                setFailed(true); setMessage(zh ? "连接检查未通过，请核对 Key、安全凭据库和服务地址后重试。" : "Connection check failed. Check the Key, secure storage and endpoint, then retry.");
              } else setMessage(selected.status === "active" ? (zh ? "连接已停用。" : "Connection disabled.") : result.credential.readiness === "ready" ? (zh ? "连接已启用。" : "Connection enabled.") : (zh ? "API 已恢复，接着测试模型能否使用。" : "Connection setup resumed. Verify a model capability to confirm availability."));
            })}>{selected.status === "active" ? (zh ? "停用" : "Disable") : (zh ? "启用" : "Enable")}</Button>
            <Button size="sm" variant="ghost" disabled={busy || !api.deleteRuntimeCredential} onClick={() => setDeleteId(selected.credential_id)}>{zh ? "删除连接" : "Delete"}</Button>
          </div>
          {deleteId === selected.credential_id ? <div className="runtime-delete-confirm" role="alert"><p>{zh ? "删除连接及其模型配置？使用它的 Agent 将需要重新配置。" : "Delete this connection and its model settings? Agents using it will need setup again."}</p><div className="button-row"><Button size="sm" disabled={busy} onClick={() => setDeleteId(null)}>{zh ? "取消" : "Cancel"}</Button><Button size="sm" variant="danger" disabled={busy} onClick={() => void run(async () => { await api.deleteRuntimeCredential!(selected.credential_id); setItems((current) => current.filter((entry) => entry.credential_id !== selected.credential_id)); setSelection(null); onSelectCredential?.(null); setDeleteId(null); window.dispatchEvent(new Event("veyra-model-registry-updated")); })}>{zh ? "确认删除" : "Delete connection"}</Button></div></div> : null}
          {replaceId === selected.credential_id ? <form className="runtime-replace-form" onSubmit={(event) => { event.preventDefault(); void run(async () => { const result = await api.replaceRuntimeCredential!(selected.credential_id, replacementKey.trim()); update(result.credential); setReplacementKey(""); setReplaceId(null); connectionMessage(result); }); }}><label className="settings-field"><span>{zh ? "新的 API Key" : "New API Key"}</span><input required name="replacement-key" disabled={busy} type="password" autoComplete="new-password" value={replacementKey} onChange={(event) => setReplacementKey(event.target.value)} /></label><div className="button-row"><Button size="sm" disabled={busy} onClick={() => { setReplaceId(null); setReplacementKey(""); }}>{zh ? "取消" : "Cancel"}</Button><Button type="submit" size="sm" variant="primary" disabled={busy || !replacementKey.trim()}>{zh ? "保存并检查" : "Save & check"}</Button></div></form> : null}
        </details>
        {renderModels?.(selected.credential_id, () => setEditConnection(selected))}
      </article>
      <p className="runtime-provider-local-note"><LockKeyhole size={14} aria-hidden="true" />{selected.readiness === "needs_reentry" ? (zh ? "密钥需要重新输入，请打开连接设置。" : "Enter the Key again in connection settings.") : (zh ? "API Key 安全保存在本机。" : "API Keys stay in secure storage on this device.")}</p>
    </> : <div className="runtime-provider-empty"><KeyRound size={24} aria-hidden="true" /><h3>{zh ? "连接你的第一个模型服务" : "Connect your first model service"}</h3><p>{zh ? "添加 API 后，选择模型并验证你需要的能力。" : "Add an API, then select a model and verify its capabilities."}</p></div>}
    {editConnection ? <SettingsDialog title={zh ? "修改服务地址" : "Edit service address"} closeLabel={zh ? "关闭" : "Close"} busy={busy} onClose={() => { if (!busy) setEditConnection(null); }}><ProviderConnectionEdit api={api} credential={editConnection} locale={locale} onBusyChange={setBusy} onBack={() => setEditConnection(null)} onSaved={(result) => { update(result.credential); connectionMessage(result); setEditConnection(null); }} /></SettingsDialog> : null}
    {open ? <SettingsDialog title={zh ? "添加模型 API" : "Add a model API"} closeLabel={zh ? "关闭" : "Close"} busy={busy} onClose={() => { if (!busy) setOpen(false); }}>
      <RuntimeProviderSetup api={api} locale={locale} onBusyChange={setBusy} onBack={() => setOpen(false)} onSaved={(result) => { update(result.credential); connectionMessage(result); setSelection(result.credential.credential_id); onSelectCredential?.(result.credential.credential_id); setOpen(false); }} />
      <p className="settings-note">{zh ? "保存时只检查连接，不会自动生成内容。模型测试由你确认后开始。" : "Connection checks read the model list. You start capability probes separately."}</p>
    </SettingsDialog> : null}
  </Panel>;
}
