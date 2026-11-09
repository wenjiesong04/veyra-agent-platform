import { useEffect, useId, useRef, useState } from "react";
import { ExternalLink } from "lucide-react";
import type { ProviderCredentialValidationResponse } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { PROVIDER_PRESETS, normalizeServiceAddress, serviceAddressIssue } from "./provider-presets";
import { connectionFailureMessage } from "./connection-feedback";

export function RuntimeProviderSetup({ api, locale, onBack, onSaved, onBusyChange }: {
  api: Pick<LocalProjectApi, "createRuntimeCredential" | "addRuntimeModel" | "replaceRuntimeCredential" | "updateRuntimeCredential">;
  locale: "zh" | "en";
  onBack: () => void;
  onSaved: (result: ProviderCredentialValidationResponse) => Promise<void> | void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const zh = locale === "zh";
  const hintId = useId();
  const [presetId, setPresetId] = useState("");
  const preset = PROVIDER_PRESETS.find((item) => item.id === presetId);
  const [customProtocol, setCustomProtocol] = useState("openai_compatible");
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [address, setAddress] = useState("");
  const [modelId, setModelId] = useState("");
  const [saved, setSaved] = useState<ProviderCredentialValidationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const custom = presetId === "openai_compatible";
  const workspaceService = presetId === "dashscope" || presetId === "dashscope_intl";
  const needsManualId = Boolean(saved && ["default_model_unavailable", "runtime_model_discovery_unavailable"].includes(saved.code));
  const retryConnection = Boolean(saved && !saved.valid && !needsManualId);
  const modelInput = useRef<HTMLInputElement>(null);
  const keyInput = useRef<HTMLInputElement>(null);
  const addressInput = useRef<HTMLInputElement>(null);
  const addressIssue = address ? serviceAddressIssue(address, locale) : "";
  useEffect(() => {
    if (busy) return;
    if (needsManualId) modelInput.current?.focus();
    else if (retryConnection) keyInput.current?.focus();
  }, [needsManualId, retryConnection, busy]);

  const save = async () => {
    if (!api.createRuntimeCredential || !preset) return;
    const normalized = normalizeServiceAddress(address);
    const issue = serviceAddressIssue(normalized, locale);
    if ((!saved || retryConnection) && issue) { setError(issue); addressInput.current?.focus(); return; }
    setBusy(true); onBusyChange?.(true); setError("");
    try {
      const connectionLabel = label.trim() || preset[locale];
      let result = saved;
      if (retryConnection && result) {
        if (!api.replaceRuntimeCredential || !key.trim()) return;
        if (api.updateRuntimeCredential) await api.updateRuntimeCredential(result.credential.credential_id, { label: connectionLabel, base_url: normalized, ...(modelId.trim() ? { default_model_id: modelId.trim() } : {}) });
        result = await api.replaceRuntimeCredential(result.credential.credential_id, key.trim());
      } else if (!result) result = await api.createRuntimeCredential({ provider_type: custom ? customProtocol : preset.providerType, label: connectionLabel, api_key: key.trim(), base_url: normalized, ...(modelId.trim() ? { default_model_id: modelId.trim() } : {}) });
      setSaved(result); setKey("");
      if (!result.valid && result.code !== "runtime_model_discovery_unavailable") { setError(connectionFailureMessage(result.code, locale)); return; }
      const missing = ["default_model_unavailable", "runtime_model_discovery_unavailable"].includes(result.code);
      if (missing && !modelId.trim()) {
        setError(zh ? "API 已保存。这个平台没有提供模型列表，请从平台的模型页面复制模型名称后继续。" : "API saved. This platform did not provide a model list. Copy a model name from its model page to continue.");
        return;
      }
      if (missing && api.addRuntimeModel) {
        const model = await api.addRuntimeModel(result.credential.credential_id, { provider_model_id: modelId.trim() });
        await onSaved({ ...result, models: [...(result.models ?? []), model] });
      } else await onSaved(result);
    } catch (cause) { setError(connectionFailureMessage(cause instanceof LocalApiClientError ? cause.code : "", locale)); }
    finally { setBusy(false); onBusyChange?.(false); }
  };

  const serviceAddress = <label className="provider-address-field provider-setup-wide"><span>{zh ? "服务地址" : "Service address"}</span><input ref={addressInput} name="provider-base-url" autoComplete="off" spellCheck={false} required disabled={busy} type="url" placeholder="https://api.example.com/v1…" value={address} onChange={(event) => setAddress(event.target.value)} /><small>{zh ? "从密钥页面或接入说明复制“API Host / 服务地址”。百炼新模型请使用“业务空间管理 → 详情”里的专属地址，不能用控制台网页。" : "Copy the API Host/service address from the key page or connection guide. New workspace models need their dedicated address, not the console webpage."}</small>{addressIssue ? <span className="provider-field-error">{addressIssue}</span> : null}</label>;
  return <form className="runtime-provider-setup" onSubmit={(event) => { event.preventDefault(); void save(); }}>
    <div><h3>{zh ? "添加模型 API" : "Add a model API"}</h3><p>{zh ? "选择你获取 API 的平台，粘贴密钥，Veyra 会帮助检查连接并查找模型。" : "Select the platform that supplied your API, paste its key, and Veyra will check the connection and find models."}</p></div>
    {!saved || retryConnection ? <>
      <label className="provider-setup-wide"><span>{zh ? "你的 API 来自哪个平台？" : "Provider"}</span><select name="provider-type" disabled={Boolean(saved) || busy} value={presetId} onChange={(event) => { const next = PROVIDER_PRESETS.find((item) => item.id === event.target.value); setPresetId(event.target.value); setAddress(next?.address ?? ""); setError(""); }}><option value="">{zh ? "选择服务商" : "Select a Provider"}</option>{PROVIDER_PRESETS.map((item) => <option key={item.id} value={item.id}>{item[locale]}</option>)}</select></label>
      {preset?.help ? <p className="provider-setup-help">{zh ? "还没有密钥？" : "Need an API key?"} <a href={preset.help} target="_blank" rel="noreferrer">{zh ? "查看获取方法" : "See how to get one"}<ExternalLink size={12} aria-hidden="true" /></a></p> : null}
      {custom || workspaceService ? serviceAddress : preset ? <p className="provider-setup-hint">{zh ? "官方服务地址已自动填写。专用地址或转发地址可在“连接选项”中修改。" : "The official service address is filled in. Change it in Connection options for a dedicated or relay endpoint."}</p> : null}
      <label className="provider-setup-wide"><span>{zh ? "API 密钥" : "API Key"}</span><input ref={keyInput} aria-label={zh ? "API 密钥" : "API Key"} aria-describedby={`${hintId}-key`} name="provider-api-key" required disabled={busy || !preset} type="password" autoComplete="new-password" value={key} onChange={(event) => setKey(event.target.value)} placeholder={zh ? "粘贴平台提供的完整密钥…" : "Paste the complete API key…"} /><small id={`${hintId}-key`}>{zh ? "密钥安全保存在本机，仅发送给你选择的模型服务。" : "The key is stored securely on this device and sent only to the selected model service."}</small></label>
      <label className="provider-setup-wide"><span>{zh ? "连接名称（可选）" : "Connection name (optional)"}</span><input aria-label={zh ? "连接名称" : "Connection name"} name="connection-name" autoComplete="off" disabled={busy} value={label} onChange={(event) => setLabel(event.target.value)} placeholder={zh ? "不填则使用服务商名称…" : "Leave blank to use the Provider name…"} /></label>
      <details className="provider-setup-options"><summary>{zh ? "连接选项" : "Connection options"}</summary><div>{!custom && !workspaceService ? serviceAddress : custom ? <label><span>{zh ? "接口格式（仅服务商有要求时修改）" : "API format (only if required)"}</span><select name="custom-protocol" value={customProtocol} disabled={busy} onChange={(event) => setCustomProtocol(event.target.value)}><option value="openai_compatible">{zh ? "通用格式（大多数 API 平台）" : "Standard format (most API platforms)"}</option><option value="anthropic">{zh ? "Claude 格式" : "Claude format"}</option></select></label> : <p>{zh ? "如未提供专用地址，可使用上面默认的公共地址；新版图片模型请优先填写业务空间专属地址。" : "Use the public default only when no dedicated address is supplied. Prefer a workspace address for newer image models."}</p>}
        <label><span>{zh ? "指定模型（可选）" : "Model ID (optional)"}</span><input ref={needsManualId ? undefined : modelInput} aria-label={zh ? "模型 ID" : "Model ID"} name="provider-model-id" autoComplete="off" spellCheck={false} disabled={busy} value={modelId} onChange={(event) => setModelId(event.target.value)} placeholder={zh ? "服务商提供的模型名称…" : "Model name supplied by the Provider…"} /><small>{zh ? "通常可以留空，保存后再从模型列表选择。" : "Usually leave blank and choose from the model list after saving."}</small></label>
      </div></details>
    </> : null}
    {needsManualId ? <label className="provider-setup-wide"><span>{zh ? "模型名称" : "Model ID"}</span><input ref={modelInput} aria-label={zh ? "模型 ID" : "Model ID"} name="manual-provider-model-id" autoComplete="off" spellCheck={false} required disabled={busy} value={modelId} onChange={(event) => setModelId(event.target.value)} /><small>{zh ? "从服务商的模型页面复制准确名称，例如 qwen-image-3.0。" : "Copy the exact model name from the Provider's model page."}</small></label> : null}
    {error ? <p className="runtime-setup-feedback" role="alert">{error}</p> : null}
    <div className="runtime-setup-form-actions"><Button type="button" variant="secondary" disabled={busy} onClick={onBack}>{zh ? "返回" : "Back to models"}</Button><Button type="submit" variant="primary" disabled={busy || !api.createRuntimeCredential || !preset || (retryConnection ? !key.trim() || Boolean(addressIssue) : saved ? needsManualId && !modelId.trim() : !key.trim() || !address.trim() || Boolean(addressIssue))}>{busy ? (zh ? "正在检查 API…" : "Checking API…") : retryConnection ? (zh ? "重新检查连接" : "Recheck connection") : needsManualId ? (zh ? "添加此模型" : "Add this model") : saved ? (zh ? "选择并测试模型" : "Continue setup") : (zh ? "保存并检查 API" : "Save & check connection")}</Button></div>
  </form>;
}
