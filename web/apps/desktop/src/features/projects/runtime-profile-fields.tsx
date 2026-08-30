import type { RuntimeApiProfileInput, RuntimeApiProfileSummary } from "@veyra/api-contracts";

type RuntimeProfileFieldsProps = {
  value: RuntimeApiProfileInput | null;
  onChange: (value: RuntimeApiProfileInput | null) => void;
  locale: "zh" | "en";
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

export function RuntimeProfileFields({ value, onChange, locale }: RuntimeProfileFieldsProps) {
  const zh = locale === "zh";
  const enabled = value !== null;
  const current = value ?? DEFAULT_PROFILE;
  const update = (field: keyof RuntimeApiProfileInput, next: string) => onChange({ ...current, [field]: next });
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
      <small className="runtime-profile-note">{zh ? "这里只保存调用配置；真正的 API Key 保留在 .env 或系统 Keychain，不会写入项目文件。" : "Only connection metadata is saved here. The API key stays in .env or the system Keychain and never enters the Project file."}</small>
    </div> : <small className="runtime-profile-note">{zh ? "启用后，运行时会优先使用这里的 API；Agent 可覆盖项目配置。" : "When enabled, Runs prefer this API. An Agent can override the Project profile."}</small>}
  </fieldset>;
}
