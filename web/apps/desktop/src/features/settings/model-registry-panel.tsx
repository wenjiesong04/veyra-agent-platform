import * as React from "react";
import { ArrowUpRight, ChevronDown, RefreshCw } from "lucide-react";
import { MODEL_CAPABILITY_NAMES, type ModelCapabilityName, type ModelDefault, type ModelProfile, type ProviderCredential } from "@veyra/api-contracts";
import { Button, Panel, StatusBadge } from "@veyra/ui";
import { useProjectWorkspace } from "../../api/project-workspace";
import { serviceAddressIssue } from "../runtime/provider-presets";
import { connectionFailureMessage } from "../runtime/connection-feedback";
import { LocalApiClientError } from "../../api/local-client";
import { MODEL_CAPABILITY_GROUPS, ModelCapabilityBadge, modelCapabilityLabel } from "../runtime/model-capability-ui";
import "./model-registry-panel.css";

const probeable: ModelCapabilityName[] = ["text_generation", "structured_output", "image_input", "image_generation"];
const costly = new Set<ModelCapabilityName>(["image_input", "image_generation"]);
function taskLabel(name: ModelCapabilityName, locale: "zh" | "en"): string {
  const labels: Partial<Record<ModelCapabilityName, string>> = { text_generation: "对话与写作", image_input: "识别和分析图片", image_generation: "生成图片", structured_output: "按固定格式输出（高级）" };
  return locale === "zh" ? labels[name] ?? modelCapabilityLabel(name, locale) : modelCapabilityLabel(name, locale);
}
const groupLabels: Record<string, { zh: string; en: string }> = {
  input: { zh: "输入", en: "Input" }, generation: { zh: "生成", en: "Generation" }, agent: { zh: "结构与 Agent", en: "Structure & Agent" }, specialized: { zh: "专用能力", en: "Specialized" },
};
function verifiedFor(profile: ModelProfile, capability: ModelCapabilityName): boolean {
  const entry = profile.capabilities[capability];
  return profile.registry_ready && entry.status === "supported" && Boolean(entry.evidence && ["provider_metadata", "provider_adapter", "active_probe"].includes(entry.evidence.source));
}
function probeBlock(profile: ModelProfile, zh: boolean): string {
  if (!profile.enabled) return zh ? "此模型已停用，请先启用模型。" : "This model is disabled. Enable it first.";
  if (profile.connection_readiness === "disabled") return zh ? "连接已停用，请在连接设置中启用后验证。" : "Connection disabled. Enable it in connection settings before verifying.";
  if (profile.connection_readiness === "needs_reentry") return zh ? "API Key 已缺失，请在连接设置中替换 Key。" : "The API Key is missing. Replace it in connection settings.";
  if (profile.connection_readiness === "unavailable") return zh ? "安全凭据库不可用，请检查本机服务。" : "Secure storage is unavailable. Check the local service.";
  return "";
}
function errorMessage(cause: unknown, zh: boolean): string {
  return connectionFailureMessage(cause instanceof LocalApiClientError ? cause.code : "", zh ? "zh" : "en");
}

export function ModelRegistryPanel({ locale, credentialId, embedded = false, onEditConnection }: { locale: "zh" | "en"; credentialId?: string | null; embedded?: boolean; onEditConnection?: () => void }) {
  const { api } = useProjectWorkspace();
  const zh = locale === "zh";
  const query = new URLSearchParams(window.location.hash.split("?")[1] ?? "");
  const rawTarget = query.get("requiredCapability");
  const target = (MODEL_CAPABILITY_NAMES as readonly string[]).includes(rawTarget ?? "") ? rawTarget as ModelCapabilityName : null;
  const targetProfile = query.get("modelProfileId");
  const rawBack = query.get("returnTo");
  const back = rawBack?.startsWith("#/") ? rawBack : null;
  const [models, setModels] = React.useState<ModelProfile[]>([]);
  const [defaults, setDefaults] = React.useState<ModelDefault[]>([]);
  const [credentials, setCredentials] = React.useState<ProviderCredential[]>([]);
  const [section, setSection] = React.useState<"models" | "defaults">("models");
  const [busy, setBusy] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [failed, setFailed] = React.useState(false);
  const [feedback, setFeedback] = React.useState<Record<string, { message: string; failed: boolean }>>({});
  const [probeCapability, setProbeCapability] = React.useState<Record<string, ModelCapabilityName>>({});
  const [acknowledged, setAcknowledged] = React.useState<Record<string, boolean>>({});
  const [manualCredential, setManualCredential] = React.useState("");
  const [manualModel, setManualModel] = React.useState("");
  const [pendingFocus, setPendingFocus] = React.useState("");
  const [expanded, setExpanded] = React.useState<string | null>(targetProfile);
  const [visibleCount, setVisibleCount] = React.useState(12);
  const [pinnedModel, setPinnedModel] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [defaultRole, setDefaultRole] = React.useState<ModelCapabilityName>(target ?? "text_generation");
  const [defaultProfile, setDefaultProfile] = React.useState("");

  const load = React.useCallback(async () => {
    if (!api.listRuntimeModels) { setLoading(false); setLoadError(zh ? "本机服务尚不支持模型库。" : "The local service does not support the model registry."); return; }
    try {
      const [registry, roleDefaults, providers] = await Promise.all([
        api.listRuntimeModels(), api.listRuntimeModelDefaults?.() ?? Promise.resolve({ defaults: [] }), api.listRuntimeCredentials?.() ?? Promise.resolve({ credentials: [] }),
      ]);
      setModels(registry.models); setDefaults(roleDefaults.defaults); setCredentials(providers.credentials); setLoadError("");
      setManualCredential((current) => providers.credentials.some((item) => item.credential_id === current) ? current : providers.credentials[0]?.credential_id ?? "");
    } catch (cause) {
      setLoadError(cause instanceof LocalApiClientError && cause.status === 404
        ? (zh ? "本机服务尚未加载模型能力库。完成更新后刷新此页。" : "The local service has not loaded the Model Registry yet. Refresh after updating it.")
        : (zh ? "无法读取模型库，请检查本机服务后重试。" : "Could not load the model registry. Check the local service and retry."));
    } finally { setLoading(false); }
  }, [api, zh]);
  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => {
    const refresh = () => { void load(); };
    window.addEventListener("veyra-model-registry-updated", refresh);
    return () => window.removeEventListener("veyra-model-registry-updated", refresh);
  }, [load]);
  React.useEffect(() => { if (credentialId) setManualCredential(credentialId); setExpanded(targetProfile); setSearch(""); setPinnedModel(null); setVisibleCount(12); setMessage(""); }, [credentialId, targetProfile]);
  const manualProvider = credentials.find((entry) => entry.credential_id === manualCredential);
  const savedModelId = models.some((profile) => profile.provider_connection_id === manualCredential && profile.provider_model_id === manualProvider?.default_model_id) ? null : manualProvider?.default_model_id;
  React.useEffect(() => { setManualModel(savedModelId ?? ""); }, [manualCredential, savedModelId]);

  React.useEffect(() => {
    if (!busy && pendingFocus) {
      document.getElementById(`model-capability-${pendingFocus}`)?.focus();
      setPendingFocus("");
    }
  }, [busy, pendingFocus]);

  const mutate = async (key: string, action: () => Promise<void>) => {
    setBusy(key); setMessage(""); setFailed(false);
    try { await action(); await load(); window.dispatchEvent(new Event("veyra-model-registry-updated")); }
    catch (cause) { setFailed(true); setMessage(errorMessage(cause, zh)); }
    finally { setBusy(""); }
  };
  const probe = async (profile: ModelProfile, capability: ModelCapabilityName) => {
    if (!api.probeRuntimeModelCapability) return;
    const id = profile.model_profile_id;
    setBusy(id); setFeedback((current) => ({ ...current, [id]: { message: "", failed: false } }));
    try {
      const result = await api.probeRuntimeModelCapability(id, capability, Boolean(acknowledged[id]));
      setModels((current) => current.map((entry) => entry.model_profile_id === id ? result : entry));
      const supported = verifiedFor(result, capability);
      const unsupported = result.capabilities[capability].status === "unsupported";
      setFeedback((current) => ({ ...current, [id]: {
        failed: !supported,
        message: supported ? (zh ? `${modelCapabilityLabel(capability, locale)}测试通过，可设为这类任务的默认模型。` : `${modelCapabilityLabel(capability, locale)} verified. You can use it as the capability default.`)
          : unsupported ? (zh ? "当前模型或服务接口不支持此能力，请选择其它模型或能力。" : "This model or endpoint does not support this capability. Choose another model or capability.")
          : (zh ? "验证未通过，能力仍未确认。请检查连接配置后重试。" : "Verification failed; the capability remains unconfirmed. Check connection settings and retry."),
      } }));
    } catch (cause) { setFeedback((current) => ({ ...current, [id]: { message: errorMessage(cause, zh), failed: true } })); }
    finally { setBusy(""); setAcknowledged((current) => ({ ...current, [id]: false })); await load(); window.dispatchEvent(new Event("veyra-model-registry-updated")); }
  };

  const scoped = models.filter((profile) => !credentialId || profile.provider_connection_id === credentialId);
  const isPreferred = (profile: ModelProfile) => defaults.some((entry) => entry.model_profile_id === profile.model_profile_id && entry.role === (target ?? "text_generation")) || credentials.some((entry) => entry.credential_id === profile.provider_connection_id && entry.default_model_id === profile.provider_model_id);
  const ordered = [...scoped].filter((profile) => `${profile.display_name} ${profile.provider_model_id}`.toLowerCase().includes(search.toLowerCase())).sort((left, right) =>
    Number(right.model_profile_id === targetProfile) - Number(left.model_profile_id === targetProfile) || Number(right.model_profile_id === pinnedModel) - Number(left.model_profile_id === pinnedModel) || (target ? Number(verifiedFor(right, target)) - Number(verifiedFor(left, target)) : 0) || Number(isPreferred(right)) - Number(isPreferred(left)) || left.provider_label.localeCompare(right.provider_label) || left.provider_model_id.localeCompare(right.provider_model_id));
  const preferred = ordered.find((profile) => defaults.some((entry) => entry.model_profile_id === profile.model_profile_id && entry.role === (target ?? "text_generation")))
    ?? ordered.find((profile) => credentials.some((entry) => entry.credential_id === profile.provider_connection_id && entry.default_model_id === profile.provider_model_id))
    ?? ordered[0];
  const activeId = expanded === "" ? "" : ordered.some((profile) => profile.model_profile_id === expanded) ? expanded : preferred?.model_profile_id;
  const candidates = models.filter((profile) => verifiedFor(profile, defaultRole));
  const matching = target ? models.filter((profile) => verifiedFor(profile, target)) : [];
  const selectedProvider = credentials.find((entry) => entry.credential_id === credentialId);
  const missingDefault = Boolean(manualProvider?.default_model_id && !models.some((profile) => profile.provider_connection_id === manualCredential && profile.provider_model_id === manualProvider.default_model_id));

  return <Panel className={`model-registry-panel ${embedded ? "is-embedded" : ""}`} aria-label={zh ? "模型能力库" : "Model capability registry"}>
    {(!embedded || scoped.length > 0) ? <div className="model-registry-head"><div>{embedded ? <h3>{zh ? "可用模型" : "Models & capabilities"}</h3> : <h2>{zh ? "可用模型" : "Models & capabilities"}</h2>}{!embedded ? <p>{selectedProvider ? selectedProvider.label : (zh ? "全部连接" : "All connections")} · {zh ? "选择模型，验证你实际需要的能力。" : "Select a model and verify the capabilities you need."}</p> : null}</div><Button size="sm" icon={RefreshCw} disabled={Boolean(busy) || loading} onClick={() => { setLoading(true); void load(); }}>{zh ? "刷新" : "Refresh"}</Button></div> : null}
    {target ? <div className="model-registry-target" role="status"><strong>{zh ? `当前需要：${taskLabel(target, locale)}` : `Needed now: ${taskLabel(target, locale)}`}</strong><span>{matching.length ? (zh ? `已有 ${matching.length} 个具备当前有效能力证据的模型。` : `${matching.length} models have current capability evidence.`) : (zh ? "还没有具备当前有效能力证据的兼容模型。" : "No compatible model has current capability evidence yet.")}</span>{!probeable.includes(target) ? <span>{zh ? "此能力暂不支持主动探测；需要 Provider 元数据或适配器提供证据。" : "Active probing is not available for this capability yet; Provider metadata or an adapter must supply evidence."}</span> : null}{matching.length && back ? <a href={back}>{zh ? "返回继续配置" : "Return to setup"}<ArrowUpRight size={14} aria-hidden="true" /></a> : null}</div> : null}
    {(!embedded || scoped.length > 0) ? <div className="model-registry-tabs" aria-label={zh ? "模型设置" : "Model settings"}><button type="button" aria-pressed={section === "models"} onClick={() => setSection("models")}>{zh ? `模型 ${scoped.length}` : `Models ${scoped.length}`}</button><button type="button" aria-pressed={section === "defaults"} onClick={() => setSection("defaults")}>{zh ? "默认模型" : "Capability defaults"}</button></div> : null}
    {message ? <p className={`settings-feedback ${failed ? "is-error" : ""}`} role={failed ? "alert" : "status"}>{message}</p> : null}
    {loading ? <p role="status">{zh ? "正在读取模型库…" : "Loading model registry…"}</p> : loadError ? <div className="settings-feedback is-error" role="alert">{loadError}<Button size="sm" onClick={() => void load()}>{zh ? "重试" : "Retry"}</Button></div> : section === "models" ? <>
      {scoped.length > 5 ? <label className="model-registry-search"><span>{zh ? "查找模型" : "Find a model"}</span><input name="model-search" type="search" autoComplete="off" value={search} onChange={(event) => { setSearch(event.target.value); setVisibleCount(12); }} placeholder={zh ? "模型名称或 ID…" : "Model name or ID…"} /></label> : null}
      {ordered.length ? <div className="model-registry-list">{ordered.slice(0, visibleCount).map((profile) => {
        const id = profile.model_profile_id;
        const selected = probeCapability[id] ?? (target && probeable.includes(target) ? target : "text_generation");
        const verified = MODEL_CAPABILITY_NAMES.some((name) => verifiedFor(profile, name));
        const connection = credentials.find((entry) => entry.credential_id === profile.provider_connection_id);
        const badAddress = connection ? serviceAddressIssue(connection.base_url, locale) : "";
        const blocking = badAddress || probeBlock(profile, zh);
        const lastError = feedback[id]?.message ? feedback[id] : profile.verification.error_code ? { message: connectionFailureMessage(profile.verification.error_code, locale), failed: true } : null;
        const opened = activeId === id;
        const supported = MODEL_CAPABILITY_NAMES.filter((name) => profile.capabilities[name].status === "supported");
        return <article className={`model-profile-card ${opened ? "is-target" : ""}`} key={id}>
          <div className="model-profile-head"><div><h3><button className="model-profile-select" type="button" aria-expanded={opened} aria-controls={opened ? `model-details-${id}` : undefined} onClick={() => setExpanded(opened ? "" : id)}><span translate="no">{profile.display_name}</span><ChevronDown size={16} aria-hidden="true" /></button></h3>{!embedded || profile.display_name !== profile.provider_model_id ? <small>{embedded ? profile.provider_model_id : profile.provider_label}{!embedded && profile.display_name !== profile.provider_model_id ? ` · ${profile.provider_model_id}` : ""}</small> : null}</div><StatusBadge label={verified ? profile.verification.source === "active_probe" ? (zh ? "测试通过" : "Actively verified") : (zh ? "已确认可用" : "Capability evidence") : (profile.verification.state === "failed" || profile.verification.error_code) ? (zh ? "测试未通过" : "Verification failed") : profile.verification.state === "stale" ? (zh ? "需要重新测试" : "Stale") : (zh ? "尚未测试" : "Unverified")} tone={verified ? "good" : (profile.verification.state === "failed" || profile.verification.error_code) ? "bad" : "warn"} /></div>
          {supported.length ? <div className="model-profile-summary">{supported.slice(0, 6).map((name) => <ModelCapabilityBadge key={name} name={name} capability={profile.capabilities[name]} locale={locale} stale={!profile.registry_ready} />)}</div> : null}
          {opened ? <div id={`model-details-${id}`} className="model-profile-workspace">
            {!supported.length ? <p className="model-profile-unknown">{zh ? "模型已添加。选择你想让它完成的任务，再测试是否可用。" : "Model registered with no confirmed capabilities. Choose a capability to verify."}</p> : null}
            <div className="model-profile-actions"><label><span>{zh ? "想用这个模型做什么？" : "Actively verify"}</span><select id={`model-capability-${id}`} name="probe-capability" disabled={Boolean(busy)} value={selected} onChange={(event) => { setProbeCapability((current) => ({ ...current, [id]: event.target.value as ModelCapabilityName })); setAcknowledged((current) => ({ ...current, [id]: false })); setFeedback((current) => ({ ...current, [id]: { message: "", failed: false } })); }}>{probeable.map((name) => <option key={name} value={name}>{taskLabel(name, locale)}</option>)}</select></label><Button size="sm" variant="primary" disabled={Boolean(busy) || Boolean(blocking) || !api.probeRuntimeModelCapability || (costly.has(selected) && !acknowledged[id])} onClick={() => void probe(profile, selected)}>{busy === id ? (zh ? "测试中…" : "Verifying…") : (zh ? "测试" : "Verify")}</Button></div>
            {blocking ? <div className="settings-feedback is-error"><p>{badAddress ? (zh ? "服务地址无效，请先修正后测试。" : "Correct the service address before testing.") : blocking}</p>{badAddress && onEditConnection ? <Button size="sm" onClick={onEditConnection}>{zh ? "修正服务地址" : "Correct service address"}</Button> : null}</div> : costly.has(selected) ? <label className="model-probe-cost"><input type="checkbox" disabled={Boolean(busy)} checked={Boolean(acknowledged[id])} onChange={(event) => setAcknowledged((current) => ({ ...current, [id]: event.target.checked }))} /><span>{zh ? "允许发送一次测试请求，费用由服务商按用量计算。" : "This probe calls the model and may incur a small API charge."}</span></label> : <p className="model-probe-note">{zh ? "会发送一次简短测试请求，费用由服务商按用量计算。" : "Verification sends a short test request and may incur a small API charge."}</p>}
            {!api.probeRuntimeModelCapability ? <p className="model-probe-note">{zh ? "本机服务暂不支持能力验证，请更新后重试。" : "Capability verification is unavailable. Update the local service and retry."}</p> : null}
            {!badAddress && lastError ? <div className={`settings-feedback ${lastError.failed ? "is-error" : ""}`} role={lastError.failed ? "alert" : "status"}><p>{lastError.message}</p>{lastError.failed && onEditConnection ? <Button size="sm" onClick={onEditConnection}>{zh ? "检查服务地址" : "Check service address"}</Button> : null}{lastError.failed && profile.verification.error_code ? <details className="model-check-diagnostic"><summary>{zh ? "检查详情" : "Check details"}</summary><code>{profile.verification.error_code}</code></details> : null}</div> : null}
            {verifiedFor(profile, selected) && api.setRuntimeModelDefault ? <Button size="sm" variant="secondary" disabled={Boolean(busy) || defaults.some((entry) => entry.role === selected && entry.model_profile_id === id)} onClick={() => void mutate("default", async () => { await api.setRuntimeModelDefault!(selected, id); setMessage(zh ? "默认模型已保存。" : "Capability default saved."); })}>{defaults.some((entry) => entry.role === selected && entry.model_profile_id === id) ? (zh ? "已用于此类任务" : "Default for this capability") : (zh ? "设为此类任务的默认模型" : "Use as capability default")}</Button> : null}
            <details className="model-profile-details"><summary>{zh ? "支持哪些用途" : "All capabilities & evidence"}</summary>{MODEL_CAPABILITY_GROUPS.map((group) => <div key={group.key}><h4>{groupLabels[group.key]?.[locale]}</h4><div>{group.names.map((name) => <ModelCapabilityBadge key={name} name={name} capability={profile.capabilities[name]} locale={locale} stale={!profile.registry_ready} />)}</div></div>)}<p>{zh ? "最近验证：" : "Last verified: "}{profile.verification.verified_at ? new Date(profile.verification.verified_at).toLocaleString(zh ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" }) : (zh ? "尚未验证" : "Never")}</p></details>
          </div> : null}
        </article>;
      })}</div> : embedded ? search ? <p className="model-profile-unknown">{zh ? "没有匹配的模型。" : "No matching models."}</p> : null : <div className="model-registry-empty"><h3>{search ? (zh ? "没有匹配的模型" : "No matching models") : (zh ? "此连接还没有模型" : "No models for this connection")}</h3><p>{search ? (zh ? "尝试其它名称或清空搜索。" : "Try another name or clear the search.") : (zh ? "服务商可能没有返回模型目录。在下方填写模型 ID，即可继续验证。" : "The Provider may not return a model list. Enter a model ID below to continue verification.")}</p></div>}
      {ordered.length > visibleCount ? <Button size="sm" variant="ghost" onClick={() => setVisibleCount((current) => current + 24)}>{zh ? `显示更多模型（还有 ${ordered.length - visibleCount} 个）` : `Show more models (${ordered.length - visibleCount} remaining)`}</Button> : null}
      {credentials.length ? <div className="model-registry-provider-tools"><div className="model-registry-tools-head"><h3>{zh ? "添加模型" : "Add a model"}</h3><Button size="sm" variant="ghost" disabled={Boolean(busy) || !manualCredential || !api.discoverRuntimeModels} onClick={() => void mutate("discovery", async () => { const result = await api.discoverRuntimeModels!(manualCredential); const ok = result.discovery.state === "ready"; setFailed(!ok); setMessage(ok ? (zh ? `目录已更新，发现 ${result.discovery.models_found} 个模型。` : `Model list updated; ${result.discovery.models_found} models found.`) : (zh ? "未能获取模型目录，可填写模型 ID 后验证。" : "Could not retrieve the model list. Enter a model ID and verify it.")); })}>{busy === "discovery" ? (zh ? "检查目录中…" : "Checking list…") : (zh ? "重新获取目录" : "Reload model list")}</Button></div>
        {missingDefault ? <p className="model-manual-hint">{zh ? "服务商没有列出这个模型，已填入你保存的名称。添加后即可测试。" : "The model was not listed. Its saved ID is prefilled for registration and verification."}</p> : null}
        <form className="model-registry-manual" onSubmit={(event) => { event.preventDefault(); if (!api.addRuntimeModel || !manualModel.trim() || !manualCredential) return; void mutate("manual", async () => { const added = await api.addRuntimeModel!(manualCredential, { provider_model_id: manualModel.trim() }); setModels((current) => [...current.filter((entry) => entry.model_profile_id !== added.model_profile_id), added]); setExpanded(added.model_profile_id); setPinnedModel(added.model_profile_id); setPendingFocus(added.model_profile_id); setVisibleCount(12); setSearch(""); setManualModel(""); setMessage(zh ? "模型已添加，接着测试能否完成你的任务。" : "Model added. Verify the capabilities you need next."); }); }}>
          {!credentialId ? <label><span>Provider</span><select name="manual-provider" disabled={Boolean(busy)} value={manualCredential} onChange={(event) => setManualCredential(event.target.value)}>{credentials.map((item) => <option key={item.credential_id} value={item.credential_id}>{item.label}</option>)}</select></label> : null}<label><span>{zh ? "模型名称" : "Model ID"}</span><input name="manual-model-id" autoComplete="off" spellCheck={false} required value={manualModel} disabled={Boolean(busy)} onChange={(event) => setManualModel(event.target.value)} placeholder={zh ? "从服务商模型页面复制准确名称…" : "Provider model ID…"} /></label><Button type="submit" size="sm" variant={scoped.length ? "secondary" : "primary"} disabled={Boolean(busy) || !manualCredential || !manualModel.trim() || !api.addRuntimeModel}>{busy === "manual" ? (zh ? "添加中…" : "Adding…") : (zh ? "添加并测试" : "Add & verify")}</Button>
        </form>
      </div> : <p className="model-profile-unknown">{zh ? "先在左侧添加 API 连接，然后选择模型。" : "Add an API connection to select a model."}</p>}
      <details className="model-registry-help"><summary>{zh ? "模型测试说明" : "About capability verification"}</summary><p className="model-probe-note">{zh ? "模型目录只证明模型存在。未提供主动验证入口的能力，需要服务商元数据或适配器证据。" : "A model list confirms availability only. Other capabilities need Provider metadata or adapter evidence."}</p></details>
    </> : <div className="model-registry-defaults"><p>{zh ? "为文字对话、看图、生成图片等任务分别选择默认模型。这里只显示已确认可用的模型。" : "Choose a default for each capability. Only models with current evidence and an available connection appear here."}</p><form className="model-registry-default-form" onSubmit={(event) => { event.preventDefault(); if (!api.setRuntimeModelDefault || !defaultProfile) return; void mutate("default", async () => { await api.setRuntimeModelDefault!(defaultRole, defaultProfile); setMessage(zh ? "默认模型已保存。" : "Capability default saved."); }); }}><label><span>{zh ? "使用场景" : "Capability role"}</span><select name="default-capability" disabled={Boolean(busy)} value={defaultRole} onChange={(event) => { setDefaultRole(event.target.value as ModelCapabilityName); setDefaultProfile(""); }}>{MODEL_CAPABILITY_NAMES.map((name) => <option key={name} value={name}>{taskLabel(name, locale)}</option>)}</select></label><label><span>{zh ? "可用模型" : "Model with current evidence"}</span><select name="default-model" disabled={Boolean(busy)} value={defaultProfile} onChange={(event) => setDefaultProfile(event.target.value)}><option value="">{zh ? "选择模型" : "Select a model"}</option>{candidates.map((profile) => <option key={profile.model_profile_id} value={profile.model_profile_id}>{profile.provider_label} · {profile.display_name}</option>)}</select></label><Button type="submit" size="sm" variant="primary" disabled={Boolean(busy) || !defaultProfile || !api.setRuntimeModelDefault}>{zh ? "保存默认值" : "Save default"}</Button></form>{!candidates.length ? <p className="model-probe-note">{zh ? "此能力还没有可用模型，请先在模型页验证。" : "No available model for this capability. Verify one in Models first."}</p> : null}{defaults.length ? <ul>{defaults.map((entry) => <li key={entry.role}><strong>{(MODEL_CAPABILITY_NAMES as readonly string[]).includes(entry.role) ? modelCapabilityLabel(entry.role as ModelCapabilityName, locale) : entry.role}</strong><span>{models.find((item) => item.model_profile_id === entry.model_profile_id)?.display_name ?? entry.provider_model_id}</span><Button size="sm" variant="ghost" disabled={Boolean(busy) || !api.clearRuntimeModelDefault} onClick={() => void mutate("default", async () => { await api.clearRuntimeModelDefault!(entry.role); setMessage(zh ? "默认值已移除。" : "Default removed."); })}>{zh ? "移除" : "Remove"}</Button></li>)}</ul> : <p>{zh ? "尚未设置能力默认模型。" : "No capability defaults yet."}</p>}</div>}
  </Panel>;
}
