import * as React from "react";
import type { ProviderCredential } from "@veyra/api-contracts";
import { Alert, Button } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";

const providerLabels: Record<string, string> = {
  moonshot: "Moonshot",
  openai: "OpenAI",
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
  openai_compatible: "OpenAI-compatible",
};

function credentialModels(item: ProviderCredential): string[] {
  const raw = item.capabilities.models;
  const listed = Array.isArray(raw)
    ? raw.filter((value): value is string => typeof value === "string" && value.trim() !== "")
    : [];
  if (item.default_model_id && !listed.includes(item.default_model_id)) {
    return [item.default_model_id, ...listed];
  }
  return listed;
}

export function ModelRuntimeInspector({
  api,
  projectId,
  agentId,
  nodeId,
  modelRef = "model.primary",
  locale,
}: {
  api: LocalProjectApi;
  projectId: string;
  agentId?: string;
  nodeId?: string;
  modelRef?: string;
  locale: "zh" | "en";
}) {
  const zh = locale === "zh";
  const [credentials, setCredentials] = React.useState<ProviderCredential[]>([]);
  const [credentialId, setCredentialId] = React.useState("");
  const [modelId, setModelId] = React.useState("");
  const [saved, setSaved] = React.useState({ credentialId: "", modelId: "" });
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const current = credentials.find((item) => item.credential_id === credentialId);
  const models = current ? credentialModels(current) : [];

  const load = React.useCallback(async () => {
    if (!api.listRuntimeCredentials) return;
    try {
      const [listed, binding] = await Promise.all([
        api.listRuntimeCredentials(),
        api.getRuntimeBinding?.(projectId, agentId, nodeId ? `node.${nodeId}` : undefined),
      ]);
      const available = listed.credentials.filter((item) => item.status !== "disabled");
      setCredentials(available);
      const nextCredential = binding?.explicit?.credential_id
        || binding?.credential?.credential_id
        || available.find((item) => item.is_default)?.credential_id
        || available[0]?.credential_id
        || "";
      const selected = available.find((item) => item.credential_id === nextCredential);
      const nextModel = binding?.explicit?.model_id
        || binding?.binding?.model_id
        || selected?.default_model_id
        || (selected ? credentialModels(selected)[0] : "")
        || "";
      setCredentialId(nextCredential);
      setModelId(nextModel);
      setSaved({
        credentialId: binding?.explicit?.credential_id || "",
        modelId: binding?.explicit?.model_id || "",
      });
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [api, projectId, agentId, nodeId]);

  React.useEffect(() => { void load(); }, [load]);

  const persist = async (nextCredential: string, nextModel: string) => {
    if (!api.setRuntimeBinding || !nextCredential || !nextModel) return;
    if (nextCredential === saved.credentialId && nextModel === saved.modelId) return;
    setBusy(true);
    setError("");
    try {
      await api.setRuntimeBinding(
        projectId,
        { credential_id: nextCredential, model_id: nextModel, ...(nodeId ? { slot: `node.${nodeId}` } : {}) },
        agentId,
      );
      setSaved({ credentialId: nextCredential, modelId: nextModel });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const addApi = () => {
    const query = new URLSearchParams({
      action: "add-provider",
      returnTo: window.location.hash,
      purpose: "agent_runtime",
    });
    window.location.hash = `#/settings?${query.toString()}`;
  };

  if (!api.listRuntimeCredentials) {
    return <p className="rail-note">{zh ? "当前 sidecar 还不支持把节点的 model_ref 映射到 User Runtime Provider。" : "This sidecar cannot map the node's model_ref to a User Runtime Provider yet."}</p>;
  }

  return (
    <section className="model-runtime-inspector" aria-label={zh ? "模型调用映射" : "Model call mapping"}>
      <label>{zh ? "调用槽位" : "Call slot"}<input value={modelRef} readOnly aria-label={zh ? "调用槽位" : "Call slot"} /></label>
      <p className="rail-note">{zh
        ? "这是调用映射：节点只保留 model_ref，真正调用哪套 User Runtime Provider / 模型写在本机绑定里，不把 API Key 或凭据写进 Agent 源文件。"
        : "This is a call mapping: the node keeps model_ref, while the User Runtime Provider and model stay in the local binding. API keys are never written into Agent source."}</p>
      {credentials.length === 0 ? (
        <div className="inspector-callout">
          <p>{zh ? "还没有可用的 User Runtime Provider。先添加自己的 API，再回到这里选择模型和凭据。" : "No User Runtime Provider is available. Add your own API, then return here to choose the credential and model."}</p>
          <Button size="sm" variant="primary" onClick={addApi}>{zh ? "添加 Provider" : "Add Provider"}</Button>
        </div>
      ) : (
        <>
          <label>{zh ? "Runtime Provider" : "Runtime Provider"}
            <select
              aria-label={zh ? "Runtime Provider" : "Runtime Provider"}
              value={credentialId}
              disabled={busy}
              onChange={(event) => {
                const next = event.target.value;
                const selected = credentials.find((item) => item.credential_id === next);
                const nextModel = selected?.default_model_id || (selected ? credentialModels(selected)[0] : "") || "";
                setCredentialId(next);
                setModelId(nextModel);
                void persist(next, nextModel);
              }}
            >
              <option value="">{zh ? "选择凭据" : "Select a credential"}</option>
              {credentials.map((item) => (
                <option key={item.credential_id} value={item.credential_id}>
                  {item.label} · {providerLabels[item.provider_type] ?? item.provider_type}
                  {item.is_default ? (zh ? " · 账号默认" : " · default") : ""}
                </option>
              ))}
            </select>
          </label>
          <label>{zh ? "模型" : "Model"}
            <select
              aria-label={zh ? "模型" : "Model"}
              value={modelId}
              disabled={busy || !credentialId || !models.length}
              onChange={(event) => {
                const next = event.target.value;
                setModelId(next);
                void persist(credentialId, next);
              }}
            >
              <option value="">{zh ? "选择模型" : "Select a model"}</option>
              {models.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <div className="button-row">
            <Button size="sm" variant="secondary" onClick={addApi}>{zh ? "添加 Provider" : "Add Provider"}</Button>
          </div>
        </>
      )}
      {current && current.readiness !== "ready" ? (
        <Alert type="warning">{zh ? "这个凭据还不能运行，请在设置中重新验证或替换 API Key。" : "This credential is not ready to run. Re-validate or replace the API key in Settings."}</Alert>
      ) : null}
      {error ? <p className="settings-secret-message" role="alert">{error}</p> : null}
    </section>
  );
}
