import * as React from "react";
import type { BuilderConversationOperation, BuilderConversationSnapshot, ProviderCredential } from "@veyra/api-contracts";
import { Alert, Button, Panel, SectionHeading, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
export function BuilderRuntimeBindingCard({
  api,
  projectId,
  conversationId,
  operation,
  locale,
  onSnapshot,
  onFollowChange,
}: {
  api: LocalProjectApi;
  projectId: string;
  conversationId: string;
  operation: BuilderConversationOperation;
  locale: "zh" | "en";
  onSnapshot: (snapshot: BuilderConversationSnapshot) => void;
  onFollowChange?: (following: boolean) => void;
}) {
  const zh = locale === "zh";
  const [credentials, setCredentials] = React.useState<ProviderCredential[]>([]);
  const [selected, setSelected] = React.useState("");
  const [model, setModel] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const waitingFor = operation.diagnostic.waiting_for;
  React.useEffect(() => {
    const request = api.listRuntimeCredentials?.();
    if (!request) return;
    void request.then((response) => {
      const available = response.credentials as ProviderCredential[];
      setCredentials(available);
      if (!selected && available[0]) {
        setSelected(available[0].credential_id);
        setModel(available[0].default_model_id ?? String((available[0].capabilities.models as unknown[] | undefined)?.[0] ?? ""));
      }
    }).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, [api, selected]);
  const current = credentials.find((item) => item.credential_id === selected);
  const models = Array.isArray(current?.capabilities.models) ? current.capabilities.models.filter((item): item is string => typeof item === "string") : [];
  const addApi = () => {
    const returnTo = window.location.hash;
    const query = new URLSearchParams({ action: "add-provider", returnTo, operationId: operation.operation_id, purpose: "agent_runtime" });
    window.location.hash = `#/settings?${query.toString()}`;
  };
  const continueBinding = async () => {
    if (!api.commandBuilderRuntimeBinding || !selected || !model) return;
    setBusy(true); setError("");
    onFollowChange?.(true);
    try {
      onSnapshot(await api.commandBuilderRuntimeBinding(projectId, conversationId, operation.operation_id, { credential_id: selected, model_id: model, confirm: true, locale, credential_scope: "device" }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { onFollowChange?.(false); setBusy(false); }
  };
  return <Panel className="builder-runtime-binding-card">
    <SectionHeading eyebrow={zh ? "Runtime Provider" : "Runtime Provider"} title={waitingFor === "waiting_for_runtime_credential" ? (zh ? "还没有可用的模型 API" : "No Runtime model API is available") : (zh ? "选择这个 Agent 的运行模型" : "Choose this Agent's Runtime model")} detail={zh ? "Builder Platform Provider 与 Agent Runtime Provider 是两个独立域。这里不会显示或上传密钥。" : "The Builder Platform Provider and Agent Runtime Provider are separate domains. Secrets are never displayed or uploaded here."} />
    {credentials.length === 0 ? <><Alert type="warning">{zh ? "Agent 需要用户自己的 Runtime Provider 才能运行。" : "This Agent needs a User Runtime Provider before it can run."}</Alert><Button variant="primary" onClick={addApi}>{zh ? "添加 API" : "Add API"}</Button></> : <>
      <label className="settings-field"><span>{zh ? "凭据" : "Credential"}</span><select value={selected} onChange={(event) => { const next = credentials.find((item) => item.credential_id === event.target.value); setSelected(event.target.value); setModel(next?.default_model_id ?? ""); }}><option value="">{zh ? "选择凭据" : "Select a credential"}</option>{credentials.map((item) => <option key={item.credential_id} value={item.credential_id}>{item.label} · {item.provider_type}</option>)}</select></label>
      <label className="settings-field"><span>{zh ? "模型" : "Model"}</span><select value={model} onChange={(event) => setModel(event.target.value)}><option value="">{zh ? "选择模型" : "Select a model"}</option>{models.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <div className="button-row"><Button variant="primary" disabled={busy || !selected || !model} onClick={() => void continueBinding()}>{zh ? "确认并继续" : "Confirm & Continue"}</Button><Button variant="secondary" onClick={addApi}>{zh ? "添加 API" : "Add API"}</Button></div>
    </>}
    {error ? <p className="settings-secret-message" role="alert">{error}</p> : null}
    <div className="settings-facts"><div><span>{zh ? "绑定状态" : "Binding status"}</span><StatusBadge label={waitingFor ?? "waiting"} tone="warn" /></div><div><span>{zh ? "作用域" : "Scope"}</span><strong>{zh ? "Project / User local" : "Project / user local"}</strong></div></div>
  </Panel>;
}
