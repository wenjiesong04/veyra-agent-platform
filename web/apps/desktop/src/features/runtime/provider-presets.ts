export type ProviderPreset = {
  id: string;
  providerType: string;
  zh: string;
  en: string;
  address: string;
  help: string;
};

// Presets fill connection data. Transport compatibility belongs to protocol drivers.
export const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: "dashscope", providerType: "openai_compatible", zh: "通义千问 · 阿里云百炼（国内）", en: "Qwen · Alibaba Model Studio (China)", address: "https://dashscope.aliyuncs.com/compatible-mode/v1", help: "https://help.aliyun.com/zh/model-studio/get-api-key" },
  { id: "dashscope_intl", providerType: "openai_compatible", zh: "通义千问 · 阿里云百炼（国际）", en: "Qwen · Alibaba Model Studio (Singapore)", address: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", help: "https://www.alibabacloud.com/help/en/model-studio/get-api-key" },
  { id: "moonshot", providerType: "moonshot", zh: "Kimi · 月之暗面", en: "Kimi · Moonshot", address: "https://api.moonshot.cn/v1", help: "https://platform.kimi.com/docs/get-api-key" },
  { id: "deepseek", providerType: "openai_compatible", zh: "DeepSeek", en: "DeepSeek", address: "https://api.deepseek.com", help: "https://api-docs.deepseek.com/" },
  { id: "siliconflow", providerType: "openai_compatible", zh: "硅基流动", en: "SiliconFlow", address: "https://api.siliconflow.cn/v1", help: "https://docs.siliconflow.cn/docs/userguide/quickstart" },
  { id: "ark", providerType: "openai_compatible", zh: "豆包 · 火山方舟", en: "Doubao · Volcengine Ark", address: "https://ark.cn-beijing.volces.com/api/v3", help: "https://www.volcengine.com/docs/82379/1399008" },
  { id: "openai", providerType: "openai", zh: "OpenAI", en: "OpenAI", address: "https://api.openai.com/v1", help: "https://platform.openai.com/api-keys" },
  { id: "anthropic", providerType: "anthropic", zh: "Claude · Anthropic", en: "Claude · Anthropic", address: "https://api.anthropic.com", help: "https://console.anthropic.com/settings/keys" },
  { id: "openrouter", providerType: "openrouter", zh: "OpenRouter", en: "OpenRouter", address: "https://openrouter.ai/api/v1", help: "https://openrouter.ai/settings/keys" },
  { id: "openai_compatible", providerType: "openai_compatible", zh: "其它平台 / API 转发服务", en: "Other platform / API relay", address: "", help: "" },
];

export function presetForAddress(value: string): ProviderPreset | undefined {
  try {
    const host = new URL(value).hostname.toLowerCase();
    const belongsTo = (domain: string) => host === domain || host.endsWith(`.${domain}`);
    const id = host === "dashscope-intl.aliyuncs.com" || host.endsWith(".ap-southeast-1.maas.aliyuncs.com") ? "dashscope_intl"
      : host === "dashscope.aliyuncs.com" || host.endsWith(".maas.aliyuncs.com") || belongsTo("bailian.console.aliyun.com") || belongsTo("modelstudio.console.alibabacloud.com") ? "dashscope"
      : belongsTo("moonshot.cn") || belongsTo("moonshot.ai") || belongsTo("kimi.com") ? "moonshot"
      : belongsTo("deepseek.com") ? "deepseek"
      : belongsTo("siliconflow.cn") || belongsTo("siliconflow.com") ? "siliconflow"
      : belongsTo("volces.com") || belongsTo("volcengine.com") ? "ark"
      : belongsTo("openai.com") ? "openai"
      : belongsTo("anthropic.com") ? "anthropic"
      : host === "openrouter.ai" ? "openrouter" : "";
    return PROVIDER_PRESETS.find((preset) => preset.id === id);
  } catch { return undefined; }
}

export function serviceAddressIssue(value: string, locale: "zh" | "en"): string {
  const zh = locale === "zh";
  try {
    const url = new URL(value.trim());
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("protocol");
    if (url.username || url.password || url.search || url.hash) return zh ? "请填写不含登录信息或密钥参数的服务地址。密钥单独填在“API 密钥”中。" : "Use a service address without login details or key parameters. Enter the API key separately.";
    const host = url.hostname.toLowerCase();
    const console = host.includes(".console.") || ["console.aliyun.com", "console.anthropic.com", "platform.openai.com", "platform.deepseek.com", "platform.moonshot.cn", "platform.kimi.com", "cloud.siliconflow.cn", "ark.volcengine.com"].includes(host)
      || host === "openrouter.ai" && /^\/(settings|dashboard|sign-in|login)/.test(url.pathname);
    if (console) return zh ? "这是账户管理或获取密钥的网页，无法调用模型。请使用服务商提供的“API Host / 服务地址”。" : "This is an account or API-key webpage, not a model service. Select the Provider to fill its service address.";
    return "";
  } catch { return zh ? "请填写服务商提供的完整服务地址，以 https:// 或 http:// 开头。" : "Enter the full service address supplied by the Provider, starting with https:// or http://."; }
}

export function normalizeServiceAddress(value: string): string {
  return value.trim().replace(/\/+$/, "").replace(/\/v1\/messages$/, "").replace(/\/(chat\/completions|images\/generations|images|models)$/, "");
}
