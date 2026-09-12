import * as React from "react";
import type { RuntimeApiProfileInput, RuntimeApiProfileSummary, RuntimeProfileValidation } from "@veyra/api-contracts";
import { Button, StatusBadge } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";

type RuntimeProfileFieldsProps = {
  value: RuntimeApiProfileInput | null;
  onChange: (value: RuntimeApiProfileInput | null) => void;
  locale: "zh" | "en";
  api: LocalProjectApi;
};

const DEFAULT_PROFILE: RuntimeApiProfileInput = {
  provider: "openai_compatible",
  base_url: "https://api.moonshot.cn/v1",
  model_id: "kimi-k3",
  api_key_env: "MOONSHOT_API_KEY",
};

export function profileInput(
  profile: RuntimeApiProfileSummary | RuntimeApiProfileInput | null | undefined,
): RuntimeApiProfileInput | null {
  if (!profile) return null;
  return {
    provider: profile.provider,
    base_url: profile.base_url,
    model_id: profile.model_id,
    api_key_env: profile.api_key_env,
  };
}

export function RuntimeProfileFields({ value, onChange, locale, api }: RuntimeProfileFieldsProps) {
  const zh = locale === "zh";
  const enabled = value !== null;
  const current = value ?? DEFAULT_PROFILE;
  const [apiKey, setApiKey] = React.useState("");
  const [checking, setChecking] = React.useState(false);
  const [validation, setValidation] = React.useState<RuntimeProfileValidation | null>(null);
  const [error, setError] = React.useState("");
  const update = (field: keyof RuntimeApiProfileInput, next: string) => {
    setValidation(null);
    setError("");
    onChange({ ...current, [field]: next });
  };
  const validate = async () => {
    if (!api.validateRuntimeProfile) return;
    setChecking(true);
    setError("");
    try {
      if (apiKey.trim()) {
        if (!api.setSecret) throw new Error(zh ? "当前 sidecar 不支持保存模型凭据。" : "This sidecar cannot save model credentials.");
        await api.setSecret("model.primary", apiKey.trim());
        setApiKey("");
      }
      setValidation(await api.validateRuntimeProfile(current));
    } catch (cause) {
      setValidation(null);
      setError(cause instanceof Error ? cause.message : (zh ? "模型 API 验证失败。" : "Model API validation failed."));
    } finally {
      setChecking(false);
    }
  };
  React.useEffect(() => {
    if (!enabled) {
      setApiKey("");
      setValidation(null);
      setError("");
    }
  }, [enabled]);
  return <fieldset className="runtime-profile-fields">
    <label className="runtime-profile-toggle">
      <input type="checkbox" checked={enabled} onChange={(event) => onChange(event.target.checked ? { ...DEFAULT_PROFILE } : null)} />
      <span>{zh ? "可调用 API（选填）" : "Callable API (optional)"}</span>
    </label>
    {enabled ? <div className="runtime-profile-grid">
      <label><span>{zh ? "Provider" : "Provider"}</span><input value={current.provider} onChange={(event) => update("provider", event.target.value)} /></label>
      <label><span>{zh ? "模型" : "Model"}</span><input value={current.model_id} onChange={(event) => update("model_id", event.target.value)} /></label>
      <label className="wide"><span>{zh ? "API 地址" : "API base URL"}</span><input type="url" value={current.base_url} onChange={(event) => update("base_url", event.target.value)} /></label>
      <label className="wide"><span>{zh ? "API Key 环境变量" : "API key environment variable"}</span><input value={current.api_key_env} onChange={(event) => update("api_key_env", event.target.value.toUpperCase())} /></label>
      <div className="runtime-profile-api wide">
        <label><span>{zh ? "模型 API Key（可选）" : "Model API key (optional)"}</span><input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => { setApiKey(event.target.value); setValidation(null); setError(""); }} placeholder="sk-…" /></label>
        <div className="runtime-profile-api-actions"><Button type="button" size="sm" variant="secondary" disabled={checking || !api.validateRuntimeProfile} onClick={() => void validate()}>{checking ? "…" : apiKey.trim() ? (zh ? "保存并验证 API" : "Save & verify API") : (zh ? "验证模型 API" : "Verify model API")}</Button>{validation ? <StatusBadge label={validation.valid ? (zh ? "验证通过" : "Verified") : (zh ? "验证失败" : "Failed")} tone={validation.valid ? "good" : "bad"} /> : null}</div>
        {validation ? <small className={validation.valid ? "runtime-profile-success" : "runtime-profile-error"}>{validation.message}</small> : null}
        {error ? <small className="runtime-profile-error">{error}</small> : null}
      </div>
      <small className="runtime-profile-note">{zh ? "这里只保存调用配置；输入的 API Key 会保存到本机 Keychain，不会写入项目文件。验证会请求 Provider 的 /models，不会发送对话内容。" : "Only connection metadata is saved here; the API key is stored in the local Keychain and never enters the Project file. Verification calls the Provider /models endpoint without sending conversation content."}</small>
    </div> : <small className="runtime-profile-note">{zh ? "启用后，运行时会优先使用这里的 API；Agent 可覆盖项目配置。" : "When enabled, Runs prefer this API. An Agent can override the Project profile."}</small>}
  </fieldset>;
}
