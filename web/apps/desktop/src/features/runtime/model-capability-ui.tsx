import type { ModelCapabilityName, ModelCapabilityRecord, ModelCapabilityStatus } from "@veyra/api-contracts";

export const MODEL_CAPABILITY_GROUPS: Array<{ key: string; names: ModelCapabilityName[] }> = [
  { key: "input", names: ["text_input", "image_input", "audio_input", "video_input"] },
  { key: "generation", names: ["text_generation", "image_generation", "image_editing", "audio_generation", "video_generation"] },
  { key: "agent", names: ["structured_output", "tool_calling", "reasoning"] },
  { key: "specialized", names: ["speech_to_text", "text_to_speech", "embeddings", "reranking"] },
];

const capabilityLabels: Record<ModelCapabilityName, { zh: string; en: string }> = {
  text_input: { zh: "文字输入", en: "Text input" },
  image_input: { zh: "图片理解", en: "Image input" },
  audio_input: { zh: "音频输入", en: "Audio input" },
  video_input: { zh: "视频输入", en: "Video input" },
  text_generation: { zh: "文字生成", en: "Text generation" },
  image_generation: { zh: "图片生成", en: "Image generation" },
  image_editing: { zh: "图片编辑", en: "Image editing" },
  audio_generation: { zh: "音频生成", en: "Audio generation" },
  video_generation: { zh: "视频生成", en: "Video generation" },
  structured_output: { zh: "结构化输出", en: "Structured output" },
  tool_calling: { zh: "工具调用", en: "Tool calling" },
  reasoning: { zh: "推理", en: "Reasoning" },
  speech_to_text: { zh: "语音转文字", en: "Speech to text" },
  text_to_speech: { zh: "文字转语音", en: "Text to speech" },
  embeddings: { zh: "向量嵌入", en: "Embeddings" },
  reranking: { zh: "重排序", en: "Reranking" },
};

const stateLabels: Record<ModelCapabilityStatus, { zh: string; en: string }> = {
  supported: { zh: "已验证", en: "Supported" },
  unsupported: { zh: "不支持", en: "Unsupported" },
  unknown: { zh: "待验证", en: "Unknown" },
};

export function modelCapabilityLabel(name: ModelCapabilityName, locale: "zh" | "en"): string {
  return capabilityLabels[name][locale];
}

export function modelCapabilityStateLabel(status: ModelCapabilityStatus, locale: "zh" | "en"): string {
  return stateLabels[status][locale];
}

export function ModelCapabilityBadge({ name, capability, locale, stale = false }: { name: ModelCapabilityName; capability: ModelCapabilityRecord; locale: "zh" | "en"; stale?: boolean }) {
  const label = modelCapabilityLabel(name, locale);
  const status = stale && capability.status !== "unknown" ? (locale === "zh" ? "需重验" : "Recheck needed") : modelCapabilityStateLabel(capability.status, locale);
  const source = capability.evidence?.source.replaceAll("_", " ") ?? (locale === "zh" ? "暂无证据" : "No evidence yet");
  return <span className="model-capability-badge" data-status={stale ? "stale" : capability.status} title={`${label} · ${status} · ${source}`}>
    <span aria-hidden="true">{stale ? "?" : capability.status === "supported" ? "✓" : capability.status === "unsupported" ? "-" : "?"}</span>
    {label}<small>{status}</small>
  </span>;
}
