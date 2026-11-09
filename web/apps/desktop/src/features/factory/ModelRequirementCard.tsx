import { MODEL_CAPABILITY_NAMES, type ModelCapabilityName, type ModelResolution } from "@veyra/api-contracts";
import { modelCapabilityLabel } from "../runtime/model-capability-ui";

const capabilityNames = new Set<string>(MODEL_CAPABILITY_NAMES);
const statuses = new Set<ModelResolution["status"]>(["already_bound", "will_bind", "needs_setup", "missing_capability", "unsupported"]);

export function proposalModels(value: unknown): ModelResolution[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const row = item as Record<string, unknown>;
    if (typeof row.slot !== "string" || typeof row.status !== "string" || !statuses.has(row.status as ModelResolution["status"])) return [];
    const names = (raw: unknown): ModelCapabilityName[] => Array.isArray(raw) ? raw.filter((name): name is ModelCapabilityName => typeof name === "string" && capabilityNames.has(name)) : [];
    const issue = row.issue && typeof row.issue === "object" && !Array.isArray(row.issue) ? row.issue as Record<string, unknown> : null;
    return [{
      slot: row.slot,
      actor_id: typeof row.actor_id === "string" ? row.actor_id : null,
      required: names(row.required), optional: names(row.optional),
      reason: typeof row.reason === "string" ? row.reason : "",
      source: typeof row.source === "string" ? row.source : "",
      status: row.status as ModelResolution["status"],
      selected_model_profile_id: typeof row.selected_model_profile_id === "string" ? row.selected_model_profile_id : null,
      selected_model_display_name: typeof row.selected_model_display_name === "string" ? row.selected_model_display_name : null,
      selected_provider_label: typeof row.selected_provider_label === "string" ? row.selected_provider_label : null,
      issue: issue ? { code: typeof issue.code === "string" ? issue.code : "", message: typeof issue.message === "string" ? issue.message : "", missing: names(issue.missing), unknown: names(issue.unknown), unsupported: names(issue.unsupported) } : null,
    }];
  });
}

export function ModelRequirementCard({ model, locale, returnTo, actorName }: { model: ModelResolution; locale: "zh" | "en"; returnTo: string; actorName?: string }) {
  const zh = locale === "zh";
  const resolved = model.status === "already_bound" || model.status === "will_bind";
  const state = resolved ? (model.status === "already_bound" ? (zh ? "已绑定" : "Bound") : (zh ? "可自动选用" : "Compatible model available")) : (zh ? "需要配置" : "Needs setup");
  const missing = [...(model.issue?.missing ?? []), ...(model.issue?.unknown ?? []), ...(model.issue?.unsupported ?? [])];
  const first = missing[0] ?? model.required[0];
  const query = new URLSearchParams({ returnTo });
  if (!model.selected_model_profile_id) query.set("action", "add-provider");
  else query.set("modelProfileId", model.selected_model_profile_id);
  if (first) query.set("requiredCapability", first);
  return <article className="factory-model-requirement" data-status={model.status}>
    <div><span className="factory-model-slot">{actorName ? `${actorName} · ` : ""}{model.slot}</span><strong>{model.required.map((name) => modelCapabilityLabel(name, locale)).join(" + ") || (zh ? "模型能力" : "Model capability")}</strong><span className="factory-model-state">{state}</span></div>
    {model.selected_model_display_name ? <p>{zh ? "候选模型：" : "Candidate model: "}{[model.selected_provider_label, model.selected_model_display_name].filter(Boolean).join(" · ")}{model.status === "will_bind" ? (zh ? "。运行前会按当前配置重新检查。" : ". It will be rechecked against current setup before running.") : ""}</p> : null}
    {model.reason ? <p>{zh ? "为什么需要：" : "Why: "}{model.reason}</p> : null}
    {model.optional.length ? <p>{zh ? "可选：" : "Optional: "}{model.optional.map((name) => modelCapabilityLabel(name, locale)).join("、")}</p> : null}
    {resolved && model.issue ? <p>{zh ? "可选能力当前不可用：" : "Optional capability unavailable: "}{missing.map((name) => modelCapabilityLabel(name, locale)).join("、") || model.issue.message}{zh ? "。如生成结构仍依赖它，运行前需要配置。" : ". Setup is required before running if the generated source still uses it."}</p> : null}
    {!resolved ? <>{([ [zh ? "缺少模型能力：" : "Missing model capability: ", model.issue?.missing], [zh ? "能力待验证：" : "Capability not verified: ", model.issue?.unknown], [zh ? "模型不支持：" : "Model does not support: ", model.issue?.unsupported] ] as Array<[string, ModelCapabilityName[] | undefined]>).map(([label, names]) => names?.length ? <p key={label}>{label}{names.map((name) => modelCapabilityLabel(name, locale)).join(zh ? "、" : ", ")}</p> : null)}{!missing.length ? <p>{model.issue?.message || (zh ? "当前没有具备有效证据的兼容模型。" : "No compatible model has current evidence.")}</p> : null}<a href={`#/settings?${query}`}>{zh ? "配置兼容模型" : "Configure a compatible model"}</a></> : null}
  </article>;
}
