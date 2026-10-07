import { useState } from "react";
import type { ProviderCredential, ProviderCredentialValidationResponse } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { connectionFailureMessage } from "../runtime/connection-feedback";
import { PROVIDER_PRESETS, normalizeServiceAddress, presetForAddress, serviceAddressIssue } from "../runtime/provider-presets";

export function ProviderConnectionEdit({ api, credential, locale, onSaved, onBack, onBusyChange }: {
  api: Pick<LocalProjectApi, "updateRuntimeCredential" | "validateRuntimeCredential">;
  credential: ProviderCredential;
  locale: "zh" | "en";
  onSaved: (result: ProviderCredentialValidationResponse) => void;
  onBack: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const zh = locale === "zh";
  const suggested = presetForAddress(credential.base_url);
  const invalidSavedAddress = Boolean(serviceAddressIssue(credential.base_url, locale));
  const [presetId, setPresetId] = useState(suggested?.providerType === credential.provider_type ? suggested.id : "openai_compatible");
  const [address, setAddress] = useState(invalidSavedAddress && suggested ? suggested.address : credential.base_url);
  const [label, setLabel] = useState(credential.label);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const issue = serviceAddressIssue(address, locale);
  const save = async () => {
    if (!api.updateRuntimeCredential || !api.validateRuntimeCredential || issue) return;
    setBusy(true); onBusyChange(true); setMessage("");
    try {
      await api.updateRuntimeCredential(credential.credential_id, { label: label.trim(), base_url: normalizeServiceAddress(address) });
      const result = await api.validateRuntimeCredential(credential.credential_id);
      onSaved(result);
    } catch (cause) { setMessage(connectionFailureMessage(cause instanceof LocalApiClientError ? cause.code : "", locale)); }
    finally { setBusy(false); onBusyChange(false); }
  };
  return <form className="provider-connection-edit" onSubmit={(event) => { event.preventDefault(); void save(); }}>
    <p>{invalidSavedAddress ? (zh ? "原地址是账户管理网页。下面已填入对应服务地址，确认后保存；原密钥会继续使用。" : "The old address is an account webpage. Review the suggested service address before saving; the stored key is reused.") : (zh ? "更改服务地址后，需要重新测试模型。原密钥会继续使用。" : "After changing the address, test the model again. The stored key is reused.")}</p>
    <label><span>{zh ? "服务商" : "Provider"}</span><select disabled={busy} value={presetId} onChange={(event) => { const preset = PROVIDER_PRESETS.find((item) => item.id === event.target.value); setPresetId(event.target.value); setAddress(preset?.address ?? ""); }}><option value="openai_compatible">{zh ? "自定义服务地址" : "Custom service address"}</option>{PROVIDER_PRESETS.filter((item) => item.id !== "openai_compatible" && item.providerType === credential.provider_type).map((item) => <option key={item.id} value={item.id}>{item[locale]}</option>)}</select></label>
    <label><span>{zh ? "服务地址" : "Service address"}</span><input name="edit-service-address" required disabled={busy} type="url" autoComplete="off" spellCheck={false} value={address} onChange={(event) => setAddress(event.target.value)} /><small>{zh ? "请优先粘贴密钥所属业务空间的“API Host”。在百炼“业务空间管理 → 详情”可以复制；地区须与密钥对应。" : "Replace this with a dedicated address if your Provider supplied one. The key must match the service region."}</small>{issue ? <span className="provider-field-error">{issue}</span> : null}</label>
    <label><span>{zh ? "连接名称" : "Connection name"}</span><input name="edit-connection-name" required disabled={busy} autoComplete="off" value={label} onChange={(event) => setLabel(event.target.value)} /></label>
    {message ? <p role="alert" className="settings-feedback is-error">{message}</p> : null}
    <div className="button-row"><Button disabled={busy} onClick={onBack}>{zh ? "取消" : "Cancel"}</Button><Button type="submit" variant="primary" disabled={busy || Boolean(issue) || !label.trim() || !api.updateRuntimeCredential || !api.validateRuntimeCredential}>{busy ? (zh ? "正在检查…" : "Checking…") : (zh ? "保存地址并检查" : "Save address & check")}</Button></div>
  </form>;
}
