import * as React from "react";
import { CheckCircle2, KeyRound, LockKeyhole, Plus, ShieldCheck, X } from "lucide-react";
import { Button, Panel, StatusBadge } from "@veyra/ui";
import { useProjectWorkspace } from "../../api/project-workspace";

type LocalRuntimeCredential = Awaited<ReturnType<NonNullable<ReturnType<typeof useProjectWorkspace>["api"]["listRuntimeCredentials"]>>>["credentials"][number];
type RuntimeCredential = {
  credential_id: string;
  label: string;
  provider_type: string;
  masked_hint: string;
  credential_scope: "device" | "cloud";
  default_model_id: string | null;
  is_default: boolean;
  status: string;
  validated_at: string | null;
  last_used_at: string | null;
  readiness: "ready" | "needs_reentry" | "unavailable" | "disabled" | "invalid" | "unverified";
};

const providerLabels: Record<string, string> = {
  moonshot: "Moonshot",
  openai: "OpenAI",
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
  openai_compatible: "OpenAI-compatible",
};

function providerLabel(value: string): string {
  return providerLabels[value] ?? value;
}

function statusLabel(item: RuntimeCredential, zh: boolean): string {
  if (item.readiness === "ready") return zh ? "可用" : "Ready";
  if (item.readiness === "needs_reentry") return zh ? "需要重新输入 Key" : "Needs Key re-entry";
  if (item.readiness === "unavailable") return zh ? "安全存储不可用" : "Secure store unavailable";
  if (item.readiness === "disabled") return zh ? "已停用" : "Disabled";
  if (item.readiness === "invalid") return zh ? "验证失败" : "Invalid";
  return zh ? "未验证" : "Unverified";
}

function statusTone(item: RuntimeCredential): "good" | "bad" | "warn" {
  if (item.readiness === "ready") return "good";
  if (item.readiness === "invalid" || item.readiness === "unavailable") return "bad";
  return "warn";
}

function formatDate(value: string | null, zh: boolean, empty: string): string {
  if (!value) return empty;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(zh ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" });
}

function localCredentialView(item: LocalRuntimeCredential): RuntimeCredential {
  return item;
}

export function ProviderCredentialsPanel({ locale }: { locale: "zh" | "en" }) {
  const { api } = useProjectWorkspace();
  const zh = locale === "zh";
  const query = new URLSearchParams(window.location.hash.split("?")[1] ?? "");
  const [items, setItems] = React.useState<RuntimeCredential[]>([]);
  const [open, setOpen] = React.useState(query.get("action") === "add-provider");
  const [provider, setProvider] = React.useState("moonshot");
  const [label, setLabel] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [model, setModel] = React.useState("");
  const [replaceId, setReplaceId] = React.useState<string | null>(null);
  const [replacementKey, setReplacementKey] = React.useState("");
  const [makeDefault, setMakeDefault] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");

  const load = React.useCallback(async () => {
    if (!api.listRuntimeCredentials) return;
    try {
      setItems((await api.listRuntimeCredentials()).credentials.map(localCredentialView));
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    }
  }, [api]);

  React.useEffect(() => { void load(); }, [load]);

  const closeModal = () => {
    if (busy) return;
    setOpen(false);
    setMessage("");
  };

  const save = async () => {
    if (!api.createRuntimeCredential || !label.trim() || !apiKey.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await api.createRuntimeCredential({
        provider_type: provider,
        label: label.trim(),
        api_key: apiKey.trim(),
        ...(baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
        ...(model.trim() ? { default_model_id: model.trim() } : {}),
        make_default: makeDefault,
      });
      const credential = localCredentialView(result.credential);
      setItems((current) => [credential, ...current.filter((item) => item.credential_id !== credential.credential_id)]);
      setApiKey("");
      setMessage(result.valid ? (zh ? "已验证。这个 Provider 现在可以用于 Agent Runtime。" : "Validated. This Provider is ready for Agent Runtime.") : result.message || (zh ? "Provider 已保存，等待验证。" : "Provider saved and awaits validation."));
      if (result.valid) {
        setOpen(false);
        const returnTo = query.get("returnTo");
        if (returnTo) window.location.hash = returnTo;
      }
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (credentialId: string, enabled: boolean) => {
    if (!api.setRuntimeCredentialStatus) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await api.setRuntimeCredentialStatus(credentialId, enabled);
      const credential = localCredentialView(result.credential);
      setItems((current) => current.map((item) => item.credential_id === credential.credential_id ? credential : item));
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (credentialId: string) => {
    if (!api.deleteRuntimeCredential) return;
    setBusy(true);
    setMessage("");
    try {
      await api.deleteRuntimeCredential(credentialId);
      setItems((current) => current.filter((item) => item.credential_id !== credentialId));
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const replace = async () => {
    if (!replaceId || !api.replaceRuntimeCredential || !replacementKey.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await api.replaceRuntimeCredential(replaceId, replacementKey.trim());
      const credential = localCredentialView(result.credential);
      setItems((current) => current.map((item) => item.credential_id === credential.credential_id ? credential : item));
      setReplacementKey("");
      setReplaceId(null);
      setMessage(result.valid ? (zh ? "已替换并验证。" : "Credential replaced and validated.") : result.message || (zh ? "替换完成，等待验证。" : "Credential replaced and awaits validation."));
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="runtime-provider-panel">
      <div className="runtime-provider-hero">
        <div className="runtime-provider-hero-copy">
          <span className="ui-eyebrow">{zh ? "账号运行环境" : "ACCOUNT RUNTIME"}</span>
          <h2>{zh ? "让你的 Agent 使用自己的模型 API" : "Let your Agents use your own model API"}</h2>
          <p>{zh ? "这里保存的是当前账号的 Runtime Provider。Builder 仍使用 Veyra 平台服务，两个凭据域完全分开。" : "These Providers belong to this account's Runtime. Builder continues to use Veyra's platform service; the two credential domains stay separate."}</p>
          <div className="runtime-provider-scope">
            <div><CheckCircle2 size={15} /><span><strong>{zh ? "用于" : "Used by"}</strong>{zh ? "Agent / Workflow 运行" : "Agent / Workflow runs"}</span></div>
            <div><ShieldCheck size={15} /><span><strong>{zh ? "不会用于" : "Never used by"}</strong>{zh ? "Builder / Proposal 生成" : "Builder / Proposal generation"}</span></div>
          </div>
        </div>
        <div className="runtime-provider-hero-action">
          <div className="runtime-provider-count"><strong>{items.length}</strong><span>{zh ? "个账号 Provider" : "account Providers"}</span></div>
          <Button icon={Plus} variant="primary" onClick={() => setOpen(true)}>{zh ? "添加 Provider" : "Add Provider"}</Button>
        </div>
      </div>

      {message ? <p className="settings-secret-message" role="status">{message}</p> : null}

      {items.length ? (
        <div className="runtime-credential-list">
          {items.map((item) => (
            <article className={`runtime-credential-card ${item.status !== "active" ? "is-inactive" : ""}`} key={item.credential_id}>
              <div className="runtime-credential-card-header">
                <div className="runtime-credential-identity">
                  <span className="runtime-credential-icon"><KeyRound size={18} /></span>
                  <div>
                    <h3>{item.label}</h3>
                  <p>{providerLabel(item.provider_type)} <span aria-hidden="true">·</span> <code>{item.masked_hint}</code> <span aria-hidden="true">·</span> {item.credential_scope === "device" ? (zh ? "本设备" : "This device") : (zh ? "云端" : "Cloud")}</p>
                  </div>
                </div>
                <div className="runtime-credential-badges">
                  <StatusBadge label={statusLabel(item, zh)} tone={statusTone(item)} />
                  {item.is_default ? <span className="runtime-default-badge">{zh ? "账号默认" : "Account default"}</span> : null}
                </div>
              </div>
              <div className="runtime-credential-facts">
                <div><span>{zh ? "默认模型" : "Default model"}</span><strong>{item.default_model_id ?? (zh ? "未设置" : "Not set")}</strong></div>
                <div><span>{zh ? "最近验证" : "Last validated"}</span><strong>{formatDate(item.validated_at, zh, zh ? "尚未验证" : "Not validated")}</strong></div>
                <div><span>{zh ? "最近使用" : "Last used"}</span><strong>{formatDate(item.last_used_at, zh, zh ? "尚未使用" : "Not used yet")}</strong></div>
              </div>
              <div className="runtime-credential-footer">
                <span className={`runtime-secret-hint ${item.readiness !== "ready" ? "is-warning" : ""}`}><LockKeyhole size={14} />{item.readiness === "needs_reentry" ? (zh ? "本地元数据仍在，但 API Key 需要重新输入" : "Metadata remains, but the API Key needs to be entered again") : item.readiness === "unavailable" ? (zh ? "系统安全凭据库不可用，暂不能运行" : "The system credential store is unavailable") : (zh ? "API Key 已安全保存，不可查看" : "API Key is stored securely and cannot be revealed")}</span>
                <div className="runtime-credential-actions">
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => { setReplaceId(item.credential_id); setReplacementKey(""); }}>{zh ? "替换 Key" : "Replace Key"}</Button>
                  <Button size="sm" variant="secondary" disabled={busy} onClick={() => void toggle(item.credential_id, item.status !== "active")}>{item.status === "active" ? (zh ? "停用" : "Disable") : (zh ? "启用" : "Enable")}</Button>
                  <Button size="sm" variant="danger" disabled={busy} onClick={() => void remove(item.credential_id)}>{zh ? "删除" : "Delete"}</Button>
                </div>
              </div>
              {replaceId === item.credential_id ? (
                <div className="runtime-replace-form">
                  <label className="settings-field"><span>{zh ? "重新输入新的 API Key" : "Enter the new API Key"}</span><input type="password" autoComplete="new-password" aria-label={zh ? "新的 API Key" : "New API Key"} value={replacementKey} onChange={(event) => setReplacementKey(event.target.value)} /></label>
                  <div className="button-row"><Button size="sm" variant="secondary" onClick={() => setReplaceId(null)}>{zh ? "取消" : "Cancel"}</Button><Button size="sm" variant="primary" disabled={busy || !replacementKey.trim()} onClick={() => void replace()}>{zh ? "替换并验证" : "Replace & Validate"}</Button></div>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="runtime-provider-empty">
          <span className="runtime-provider-empty-icon"><KeyRound size={22} /></span>
          <h3>{zh ? "还没有账号模型 API" : "No account model API yet"}</h3>
          <p>{zh ? "添加一个 Provider 后，Agent 才能在本机 Runtime 中运行。添加不会改变 Builder 的平台凭据。" : "Add a Provider before running an Agent in the local Runtime. This does not change the platform credential used by Builder."}</p>
          <Button icon={Plus} variant="secondary" onClick={() => setOpen(true)}>{zh ? "添加第一个 Provider" : "Add your first Provider"}</Button>
        </div>
      )}

      {open ? (
        <div className="runtime-provider-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeModal(); }}>
          <div className="runtime-provider-modal" role="dialog" aria-modal="true" aria-label={zh ? "添加账号 Runtime Provider" : "Add account Runtime Provider"}>
            <div className="runtime-provider-modal-header">
              <div><span className="ui-eyebrow">{zh ? "账号 Runtime" : "ACCOUNT RUNTIME"}</span><h2>{zh ? "添加模型 Provider" : "Add model Provider"}</h2><p>{zh ? "API Key 只用于验证和运行你的 Agent，不会上传到 Community，也不会交给 Builder。" : "The API Key is used only to validate and run your Agents. It is never sent to Community or Builder."}</p></div>
              <button className="runtime-provider-modal-close" type="button" aria-label={zh ? "关闭" : "Close"} onClick={closeModal}><X size={18} /></button>
            </div>
            <div className="runtime-provider-modal-note"><ShieldCheck size={16} /><span>{zh ? "Test & Save 只请求 Provider 的模型列表，不发送生成请求。" : "Test & Save only requests the Provider model list; it does not send a generation request."}</span></div>
            <form className="runtime-provider-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
              <div className="runtime-provider-form-grid">
                <label className="settings-field"><span>{zh ? "Provider 类型" : "Provider type"}</span><select value={provider} onChange={(event) => setProvider(event.target.value)}><option value="moonshot">Moonshot</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="openrouter">OpenRouter</option><option value="openai_compatible">OpenAI-compatible</option></select></label>
                <label className="settings-field"><span>{zh ? "显示名称" : "Display name"}</span><input required value={label} onChange={(event) => setLabel(event.target.value)} placeholder={zh ? "例如：我的 Moonshot" : "For example: My Moonshot"} /></label>
                <label className="settings-field runtime-provider-form-wide"><span>API Key</span><input required type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={zh ? "粘贴 API Key" : "Paste your API Key"} /></label>
                {provider === "openai_compatible" ? <label className="settings-field runtime-provider-form-wide"><span>Base URL</span><input required value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://example.com/v1" /></label> : null}
                <label className="settings-field"><span>{zh ? "默认模型（可选）" : "Default model (optional)"}</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder={provider === "moonshot" ? "kimi-k3" : "例如：gpt-4o-mini"} /></label>
              </div>
              <label className="runtime-default-toggle"><input type="checkbox" checked={makeDefault} onChange={(event) => setMakeDefault(event.target.checked)} /><span><strong>{zh ? "设为账号默认 Provider" : "Set as account default"}</strong><small>{zh ? "新 Agent 会优先使用它，但仍可在 Project/Agent 中改绑。" : "New Agents prefer it, but Project/Agent binding can override it."}</small></span></label>
              <div className="runtime-provider-modal-footer"><Button type="button" variant="secondary" onClick={closeModal}>{zh ? "取消" : "Cancel"}</Button><Button type="submit" icon={busy ? undefined : CheckCircle2} variant="primary" disabled={busy || !label.trim() || !apiKey.trim()}>{busy ? (zh ? "验证中…" : "Validating…") : (zh ? "验证并保存" : "Test & Save")}</Button></div>
            </form>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
