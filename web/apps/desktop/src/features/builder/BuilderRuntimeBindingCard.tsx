import * as React from "react";
import type { BuilderConversationOperation, BuilderConversationSnapshot, ProviderCredential } from "@veyra/api-contracts";
import { Alert, Button } from "@veyra/ui";
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
      const first = available.find((item) => item.is_default && item.readiness === "ready")
        ?? available.find((item) => item.readiness === "ready")
        ?? available[0];
      if (first) {
        setSelected((current) => current || first.credential_id);
        setModel((current) => current || first.default_model_id || String((first.capabilities.models as unknown[] | undefined)?.[0] ?? ""));
      }
    }).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, [api]);
  const current = credentials.find((item) => item.credential_id === selected);
  const models = Array.isArray(current?.capabilities.models) ? current.capabilities.models.filter((item): item is string => typeof item === "string") : [];
  const modelOptions = model && !models.includes(model) ? [model, ...models] : models;
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
  return <section className="builder-runtime-binding-card" aria-label={zh ? "运行模型设置" : "Runtime model setup"}>
    <header className="builder-runtime-binding-head">
      <div className="builder-runtime-binding-heading">
        <span className="builder-runtime-binding-eyebrow">{zh ? "运行模型" : "Runtime model"}</span>
        <h3>{waitingFor === "waiting_for_runtime_credential"
          ? (zh ? "先添加模型 API，再继续构建" : "Add a model API to continue")
          : (zh ? "选择运行模型，继续构建" : "Choose a Runtime model to continue")}</h3>
        <p>{zh
          ? "这个模型用于运行生成的 Agent。它与你用来构建方案的模型分开设置。"
          : "This model runs the Agent you create. It is configured separately from the model used to build it."}</p>
      </div>
      <span className="builder-runtime-binding-status"><span aria-hidden="true" />{zh ? "等待你选择" : "Waiting for you"}</span>
    </header>
    {credentials.length === 0 ? <div className="builder-runtime-binding-empty">
      <Alert type="warning">{zh ? "还没有可用的运行模型 API。添加后就能从这里继续。" : "No Runtime model API is available yet. Add one, then continue here."}</Alert>
      <Button variant="primary" onClick={addApi}>{zh ? "添加模型 API" : "Add model API"}</Button>
    </div> : <>
      <div className="builder-runtime-binding-fields">
        <label><span>{zh ? "模型 API" : "Model API"}</span><select value={selected} onChange={(event) => {
          const next = credentials.find((item) => item.credential_id === event.target.value);
          setSelected(event.target.value);
          setModel(next?.default_model_id ?? (Array.isArray(next?.capabilities.models) ? String(next.capabilities.models[0] ?? "") : ""));
        }}><option value="">{zh ? "选择 Provider" : "Select a provider"}</option>{credentials.map((item) => <option key={item.credential_id} value={item.credential_id}>{item.label} · {item.provider_type}</option>)}</select></label>
        <label><span>{zh ? "模型" : "Model"}</span><select value={model} onChange={(event) => setModel(event.target.value)}><option value="">{zh ? "选择模型" : "Select a model"}</option>{modelOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      </div>
      <div className="builder-runtime-binding-actions">
        <Button variant="primary" disabled={busy || !selected || !model} onClick={() => void continueBinding()}>{busy ? (zh ? "正在继续…" : "Continuing…") : (zh ? "确认并继续" : "Confirm and continue")}</Button>
        <Button variant="secondary" onClick={addApi}>{zh ? "添加其他 Provider" : "Add another provider"}</Button>
      </div>
    </>}
    {error ? <p className="builder-runtime-binding-error" role="alert">{error}</p> : null}
    <p className="builder-runtime-binding-note">{zh ? "密钥仅保存在本机，不会在这里显示。" : "The secret stays on this device and is not shown here."}</p>
  </section>;
}
