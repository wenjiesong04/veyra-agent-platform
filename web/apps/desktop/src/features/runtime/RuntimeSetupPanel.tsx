import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowUpRight, CircleAlert, RefreshCw, X } from "lucide-react";
import type { ModelCapabilityName, ModelProfile, RuntimeSetupIssue } from "@veyra/api-contracts";
import { Button } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { isElectronDesktop } from "../../electron";
import { modelCapabilityLabel } from "./model-capability-ui";
import { RuntimeProviderSetup } from "./RuntimeProviderSetup";
import "./runtime-setup.css";

type SetupGroup = {
  key: string;
  action: RuntimeSetupIssue["action"];
  code: string;
  modelProfileId?: string;
  requirement: ModelCapabilityName[];
  owners: string[];
  messages: string[];
  issues: RuntimeSetupIssue[];
};

function setupHref(group: SetupGroup, returnTo: string): string {
  const query = new URLSearchParams({ returnTo });
  if (group.action === "configure_model" && !group.modelProfileId) query.set("action", "add-provider");
  if (group.requirement[0]) query.set("requiredCapability", group.requirement[0]);
  if (group.modelProfileId) query.set("modelProfileId", group.modelProfileId);
  return `#/settings?${query}`;
}

function ownerName(issue: RuntimeSetupIssue, zh: boolean, resourceNames: Record<string, string>): string {
  if (issue.agent_id && resourceNames[issue.agent_id]) return resourceNames[issue.agent_id];
  if (issue.scope === "image_model" || issue.scope === "image") return zh ? "图片生成" : "Image generation";
  if (issue.scope === "primary_model" || issue.scope === "primary") return zh ? "主模型" : "Primary model";
  if (issue.scope.startsWith("node.")) return zh ? "模型节点" : "Model node";
  return issue.scope;
}

function groupIssues(issues: RuntimeSetupIssue[], zh: boolean, resourceNames: Record<string, string>): SetupGroup[] {
  const groups = new Map<string, SetupGroup>();
  for (const issue of issues) {
    const kind = issue.requirement.includes("image_generation") ? "image" : "primary";
    const key = issue.action === "verify_model" && issue.model_profile_id
      ? `${issue.action}:${issue.model_profile_id}:${kind}`
      : `${issue.action}:${issue.agent_id ?? ""}:${issue.scope}`;
    const group = groups.get(key) ?? { key, action: issue.action, code: issue.code, modelProfileId: issue.model_profile_id, requirement: [], owners: [], messages: [], issues: [] };
    group.issues.push(issue);
    for (const capability of issue.requirement) if (!group.requirement.includes(capability)) group.requirement.push(capability);
    const owner = ownerName(issue, zh, resourceNames);
    if (!group.owners.includes(owner)) group.owners.push(owner);
    if (issue.message && !group.messages.includes(issue.message)) group.messages.push(issue.message);
    groups.set(key, group);
  }
  return [...groups.values()];
}

function groupMessage(group: SetupGroup, zh: boolean): string {
  if (!zh) return group.messages.join(" ");
  if (group.action === "verify_model") return "当前模型尚未验证所需能力。选择模型并验证后即可继续。";
  if (group.action === "rebind_model") return "当前绑定的模型不支持这些能力，请换一个具备这些能力的模型。";
  if (group.requirement.includes("image_generation")) return "还没有可用的图片生成模型。添加支持图片生成的 Provider 并验证后即可运行。";
  return "还没有满足这些能力的可用模型。添加 Provider 并验证模型能力后即可运行。";
}

function bindingSlot(issue: RuntimeSetupIssue): string {
  const scope = issue.node_id && issue.scope.startsWith(`${issue.node_id}.`) ? issue.scope.slice(issue.node_id.length + 1) : issue.scope;
  return scope === "primary" ? "primary_model" : scope === "image" ? "image_model" : scope;
}

function compatible(profile: ModelProfile, requirements: ModelCapabilityName[]): boolean {
  return profile.registry_ready && requirements.length > 0 && requirements.every((name) => {
    const entry = profile.capabilities[name];
    return entry.status === "supported" && Boolean(entry.evidence && ["provider_metadata", "provider_adapter", "active_probe"].includes(entry.evidence.source));
  });
}

export function RuntimeSetupPanel({ issues, locale, returnTo, onRecheck, rechecking = false, resourceNames = {}, api, projectId }: {
  issues: RuntimeSetupIssue[];
  locale: "zh" | "en";
  returnTo: string;
  onRecheck?: () => void | Promise<void>;
  rechecking?: boolean;
  resourceNames?: Record<string, string>;
  api?: Pick<LocalProjectApi, "listRuntimeModels" | "setRuntimeBinding" | "probeRuntimeModelCapability" | "createRuntimeCredential" | "addRuntimeModel" | "replaceRuntimeCredential" | "updateRuntimeCredential">;
  projectId?: string;
}) {
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [addingFor, setAddingFor] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState<Record<string, boolean>>({});
  const [checking, setChecking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDivElement>(null);
  const loadProfiles = useCallback(async () => {
    if (!api?.listRuntimeModels) return;
    setLoading(true);
    try { setProfiles((await api.listRuntimeModels()).models); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setLoading(false); }
  }, [api]);
  useEffect(() => { if (open) void loadProfiles(); }, [open, loadProfiles]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLElement>("button")?.focus();
    return () => { previous?.focus(); };
  }, [open]);
  const zh = locale === "zh";
  const native = isElectronDesktop();
  const groups = groupIssues(issues, zh, resourceNames);
  const busy = saving !== null || checking || rechecking;
  const recheck = async () => {
    if (!onRecheck) return;
    setChecking(true); setError("");
    try { await onRecheck(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setChecking(false); }
  };
  useEffect(() => {
    const refresh = () => {
      if (!open || busy || addingFor) return;
      void loadProfiles();
      void Promise.resolve(onRecheck?.()).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
    };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [open, busy, addingFor, loadProfiles, onRecheck]);
  const bind = async (group: SetupGroup, profileId: string) => {
    const profile = profiles.find((item) => item.model_profile_id === profileId && compatible(item, group.requirement));
    if (!profile || !projectId || !api?.setRuntimeBinding) return;
    setSaving(group.key); setError("");
    try {
      const applied = new Set<string>();
      for (const issue of group.issues) {
        const slot = bindingSlot(issue);
        const key = `${issue.agent_id ?? "project"}:${slot}`;
        if (applied.has(key)) continue;
        await api.setRuntimeBinding(projectId, { credential_id: profile.provider_connection_id, model_id: profile.provider_model_id, slot }, issue.agent_id);
        applied.add(key);
      }
      await recheck();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSaving(null); }
  };
  const verify = async (group: SetupGroup, profile: ModelProfile) => {
    if (!api?.probeRuntimeModelCapability) return;
    setSaving(group.key); setError("");
    try {
      let updated = profile;
      for (const capability of group.requirement) {
        if (compatible(updated, [capability])) continue;
        updated = await api.probeRuntimeModelCapability(profile.model_profile_id, capability, Boolean(acknowledged[group.key]));
        setProfiles((current) => current.map((item) => item.model_profile_id === updated.model_profile_id ? updated : item));
        if (updated.capabilities[capability].status === "unsupported") {
          setError(zh ? `这个模型不支持${modelCapabilityLabel(capability, locale)}。请选择其他模型或添加对应 API。` : `This model does not support ${modelCapabilityLabel(capability, locale)}. Choose another model or add a compatible API.`);
          await onRecheck?.();
          return;
        }
      }
      if (compatible(updated, group.requirement) && projectId && api.setRuntimeBinding) {
        const applied = new Set<string>();
        for (const issue of group.issues) {
          const slot = bindingSlot(issue);
          const key = `${issue.agent_id ?? "project"}:${slot}`;
          if (applied.has(key)) continue;
          await api.setRuntimeBinding(projectId, { credential_id: updated.provider_connection_id, model_id: updated.provider_model_id, slot }, issue.agent_id);
          applied.add(key);
        }
      }
      await recheck();
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSaving(null); setAcknowledged((current) => ({ ...current, [group.key]: false })); }
  };
  if (!issues.length) return null;
  const capabilities = [...new Set(groups.flatMap((group) => group.requirement))].map((capability) => modelCapabilityLabel(capability, locale));
  const adding = groups.find((group) => group.key === addingFor);
  return <><section className="runtime-setup-status" aria-label={zh ? "运行前设置" : "Runtime setup"}>
    <CircleAlert size={19} aria-hidden="true" /><div><strong>{zh ? "运行模型还需配置" : "Model setup is needed"}</strong><p>{capabilities.join(zh ? "、" : ", ")} · {zh ? `${groups.length} 项待完成` : `${groups.length} items remaining`}</p></div>
    <div className="runtime-setup-status-actions"><Button size="sm" variant="primary" onClick={() => { setOpen(true); setAddingFor(null); setAcknowledged({}); setError(""); }}>{zh ? "配置模型" : "Set up models"}</Button>{onRecheck ? <Button size="sm" variant="ghost" icon={RefreshCw} disabled={busy} onClick={() => void recheck()}>{busy ? (zh ? "检查中…" : "Checking…") : (zh ? "重新检查" : "Recheck")}</Button> : null}</div>
  </section>{error && !open ? <p className="runtime-setup-feedback" role="alert">{error}</p> : null}{open ? createPortal(<div className="runtime-setup-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setOpen(false); }}><div className="runtime-setup-dialog" role="dialog" aria-modal="true" aria-labelledby="runtime-setup-title" ref={dialog} onKeyDown={(event) => {
    if (event.key === "Escape" && !busy) setOpen(false);
    if (event.key === "Tab") {
      const elements = [...(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled)') ?? [])];
      const first = elements[0]; const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  }}><header><div><h2 id="runtime-setup-title">{zh ? "配置运行模型" : "Set up Runtime models"}</h2><p>{zh ? "选择模型并确认能力，完成后自动检查。当前任务输入会保留。" : "Choose a model and verify its capabilities. Your current task inputs stay in place."}</p></div><button type="button" className="runtime-setup-close" aria-label={zh ? "关闭配置" : "Close setup"} disabled={busy} onClick={() => setOpen(false)}><X size={19} /></button></header>
    {adding && api ? <><p className="runtime-setup-context">{zh ? "用于：" : "Needed for: "}{adding.requirement.map((name) => modelCapabilityLabel(name, locale)).join(zh ? "、" : ", ")}</p><RuntimeProviderSetup api={api} locale={locale} onBusyChange={(active) => setSaving(active ? "provider" : null)} onBack={() => setAddingFor(null)} onSaved={async (result) => { await loadProfiles(); const profile = result.models?.find((item) => compatible(item, adding.requirement)) ?? result.models?.[0]; if (profile) setSelected((current) => ({ ...current, [adding.key]: profile.model_profile_id })); setAddingFor(null); }} /></> : <ol className="runtime-setup-list">{groups.map((group) => {
      const capabilities = group.requirement.map((capability) => modelCapabilityLabel(capability, locale));
      const choices = profiles.filter((profile) => (profile.registry_ready || profile.connection_readiness === "unverified") && !group.requirement.some((name) => profile.capabilities[name].status === "unsupported"));
      const preferred = choices.find((profile) => compatible(profile, group.requirement)) ?? choices.find((profile) => profile.model_profile_id === group.modelProfileId);
      const profile = choices.find((item) => item.model_profile_id === selected[group.key]) ?? preferred;
      const supported = profile && compatible(profile, group.requirement);
      const probeable = group.requirement.every((name) => ["text_generation", "structured_output", "image_input", "image_generation"].includes(name));
      const costly = group.requirement.some((name) => ["image_input", "image_generation"].includes(name) && (!profile || !compatible(profile, [name])));
      return <li key={group.key}>
        <div><span className="runtime-setup-scope">{group.owners.join(zh ? "、" : ", ")}</span><h3>{capabilities.join(zh ? "、" : ", ")}</h3><p>{groupMessage(group, zh)}</p></div>
        {loading ? <p>{zh ? "正在读取模型…" : "Loading models…"}</p> : choices.length ? <div className="runtime-setup-model-choice">
          <label><span>{zh ? "使用模型" : "Model to use"}</span>
            <select value={profile?.model_profile_id ?? ""} disabled={busy} onChange={(event) => {
              setSelected((current) => ({ ...current, [group.key]: event.target.value }));
              setAcknowledged((current) => ({ ...current, [group.key]: false }));
            }}>
              <option value="">{zh ? "选择要使用或验证的模型" : "Choose a model to use or verify"}</option>
              {choices.map((item) => <option key={item.model_profile_id} value={item.model_profile_id}>{item.provider_label} · {item.display_name}{compatible(item, group.requirement) ? (zh ? " · 可用" : " · Ready") : (zh ? " · 待验证" : " · Unverified")}</option>)}
            </select>
          </label>
          {!profile ? <p>{zh ? "没有已验证的兼容模型。添加对应 API，或选择现有模型进行验证。" : "No verified compatible model is available. Add an API, or choose an existing model to verify."}</p> : null}
          {profile && !supported && costly && probeable ? <label className="runtime-setup-cost">
            <input type="checkbox" disabled={busy} checked={Boolean(acknowledged[group.key])} onChange={(event) => setAcknowledged((current) => ({ ...current, [group.key]: event.target.checked }))} />
            <span>{zh ? "我同意本次验证实际调用模型，可能产生少量 API 费用。" : "I agree to this real model verification, which may incur a small API charge."}</span>
          </label> : null}
          {profile && supported && api?.setRuntimeBinding ? <Button size="sm" variant="primary" disabled={busy} onClick={() => void bind(group, profile.model_profile_id)}>{saving === group.key ? (zh ? "保存中…" : "Saving…") : (zh ? "使用此模型" : "Use this model")}</Button> :
            profile && !supported && probeable && api?.probeRuntimeModelCapability ? <Button size="sm" variant="primary" disabled={busy || (costly && !acknowledged[group.key])} onClick={() => void verify(group, profile)}>{saving === group.key ? (zh ? "正在验证模型…" : "Verifying model…") : (zh ? "验证并使用" : "Verify & use")}</Button> :
              profile && !probeable ? <p>{zh ? "此能力需要服务商提供有效的能力信息，暂不支持主动验证。" : "This capability requires trusted Provider metadata; active verification is not available yet."}</p> : null}
        </div> : <p className="runtime-setup-empty">{zh ? "当前没有合适的模型，添加对应的 API 后继续。" : "No suitable model is available. Add a compatible API to continue."}</p>}
        {group.requirement.includes("image_generation") ? <p className="runtime-setup-hint">{zh ? "图片理解与图片生成是不同能力，请选择能生成图片的模型。" : "Image input and image generation are different capabilities."}</p> : null}
        <div className="runtime-setup-row-actions">
          {api?.createRuntimeCredential ? <Button size="sm" variant={profile ? "secondary" : "primary"} disabled={busy} onClick={() => { setAddingFor(group.key); setError(""); }}>{zh ? "添加模型 API" : "Add a model API"}</Button> : null}
          <a href={setupHref(group, returnTo)} target={native ? undefined : "_blank"} rel="noopener noreferrer" aria-label={native ? undefined : (zh ? "在新标签中管理全部模型" : "Manage all models in a new tab")}>{zh ? "管理全部模型" : "Manage all models"}<ArrowUpRight size={14} aria-hidden="true" /></a>
        </div>
      </li>;
    })}</ol>}
    {error ? <p className="runtime-setup-feedback" role="alert">{error}</p> : null}
  </div></div>, document.body) : null}</>;
}
