import type { RuntimeApiProfileInput, RuntimeApiProfileSummary } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";

type RuntimeProfileFieldsProps = {
  value: RuntimeApiProfileInput | null;
  onChange: (value: RuntimeApiProfileInput | null) => void;
  locale: "zh" | "en";
  api: LocalProjectApi;
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
  void value; void onChange; void api;
  return <small className="runtime-profile-note">{locale === "zh"
    ? "Runtime Provider 已迁移到 Provider Credentials 与 Runtime Binding。此兼容组件不再接受或保存 API Key。"
    : "Runtime Providers now use Provider Credentials and Runtime Binding. This compatibility component never accepts or saves an API key."}</small>;
}
