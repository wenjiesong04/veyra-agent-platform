import type {
  CustomComponentDefinition,
  CustomComponentImplementationKind,
  CustomComponentSummary,
  CreateCustomComponentRequest,
  JsonObject,
  TypedFields,
} from "@veyra/api-contracts";
import { Button, EmptyState, ErrorState, Panel, SectionHeading, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";
import { LocalApiClientError } from "../../api/local-client";
import type { LocalProjectApi } from "../../api/local-client";

type DraftForm = {
  displayName: string;
  description: string;
  implementationKind: CustomComponentImplementationKind;
  inputs: string;
  outputs: string;
  implementation: string;
  metadata: string;
};

const implementationKinds: CustomComponentImplementationKind[] = ["model_recipe", "tool_wrapper", "transform", "composite_graph"];

const implementationTemplates: Record<CustomComponentImplementationKind, string> = {
  model_recipe: '{\n  "instruction": ""\n}',
  tool_wrapper: '{\n  "tool_reference": ""\n}',
  transform: '{\n  "mapping": {\n    "result": "{{input}}"\n  }\n}',
  composite_graph: '{\n  "graph": {\n    "nodes": [],\n    "transitions": []\n  }\n}',
};

const emptyForm = (): DraftForm => ({
  displayName: "",
  description: "",
  implementationKind: "model_recipe",
  inputs: '{\n  "prompt": "string"\n}',
  outputs: '{\n  "result": "string"\n}',
  implementation: '{\n  "instruction": ""\n}',
  metadata: "{}",
});

function jsonObject(text: string, field: string): Record<string, unknown> {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${field} must be a JSON object.`);
  return value as Record<string, unknown>;
}

function formFromDefinition(definition: CustomComponentDefinition): DraftForm {
  const { kind: _kind, ...implementation } = definition.implementation;
  return {
    displayName: definition.display_name,
    description: definition.description,
    implementationKind: definition.implementation.kind as CustomComponentImplementationKind,
    inputs: JSON.stringify(definition.inputs, null, 2),
    outputs: JSON.stringify(definition.outputs, null, 2),
    implementation: JSON.stringify(implementation, null, 2),
    metadata: JSON.stringify(definition.metadata, null, 2),
  };
}

function requestFromForm(form: DraftForm): CreateCustomComponentRequest {
  const inputs = jsonObject(form.inputs, "Inputs") as TypedFields;
  const outputs = jsonObject(form.outputs, "Outputs") as TypedFields;
  const metadata = jsonObject(form.metadata, "Metadata");
  if (Object.values(metadata).some((value) => typeof value !== "string")) throw new Error("Metadata values must all be strings.");
  const implementation = {
    kind: form.implementationKind,
    ...jsonObject(form.implementation, "Implementation"),
  } as JsonObject;
  return {
    display_name: form.displayName.trim(),
    description: form.description.trim(),
    inputs,
    outputs,
    implementation,
    metadata: metadata as Record<string, string>,
    provenance: "manual",
  };
}

function readinessLabel(value: CustomComponentSummary["versions"][number]["readiness"], zh: boolean): string {
  return zh
    ? { ready: "就绪", requires_configuration: "需要配置", design_only: "仅设计", unavailable: "不可用" }[value]
    : { ready: "Ready", requires_configuration: "Needs configuration", design_only: "Design only", unavailable: "Unavailable" }[value];
}

function versionHint(summary: CustomComponentSummary, zh: boolean): string {
  if (summary.draft) return zh ? "有未发布草稿" : "Draft changes are unpublished";
  if (!summary.latest_version) return zh ? "尚未发布" : "Not published";
  return `${zh ? "最新版本" : "Latest version"}: ${summary.latest_version}`;
}

export function CustomComponentsPanel({
  api,
  projectId,
  onChanged,
}: {
  api: LocalProjectApi;
  projectId: string;
  onChanged?: () => void | Promise<void>;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [components, setComponents] = useState<CustomComponentSummary[]>([]);
  const [form, setForm] = useState<DraftForm>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [validatedComponentId, setValidatedComponentId] = useState<string | null>(null);
  const interactionsDisabled = busy || loading || error !== null;

  const load = useCallback(async () => {
    if (!api.listCustomComponents) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.listCustomComponents(projectId);
      if (result.project_id !== projectId) throw new Error("Project identity mismatch.");
      setComponents(result.components);
    } catch (cause) {
      setError(cause instanceof LocalApiClientError && cause.status === 404
        ? (zh
          ? "组件列表 API 返回 404。当前本地服务可能尚未提供组件接口，或项目不可用。表单已锁定；更新/重启本地服务后请重试。未提交的内容不会保存。"
          : "The Custom Component list API returned 404. This local service may not expose the component API, or the Project may be unavailable. Editing is locked; update/restart the local service, then retry. Nothing has been saved.")
        : cause instanceof Error ? cause.message : (zh ? "无法加载自定义组件。" : "Could not load Custom Components."));
    } finally {
      setLoading(false);
    }
  }, [api, projectId, zh]);

  useEffect(() => { void load(); }, [load]);

  const startNew = () => {
    setEditingId(null);
    setValidatedComponentId(null);
    setForm(emptyForm());
    setError(null);
    setMessage(null);
  };

  const updateForm = (patch: Partial<DraftForm>) => {
    setValidatedComponentId(null);
    setForm((current) => ({ ...current, ...patch }));
  };

  const edit = async (summary: CustomComponentSummary) => {
    if (!api.getCustomComponent) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const definition = summary.draft ?? await api.getCustomComponent(projectId, summary.component_id);
      setEditingId(summary.component_id);
      setValidatedComponentId(null);
      setForm(formFromDefinition(definition));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load the Custom Component.");
    } finally {
      setBusy(false);
    }
  };

  const saveDraft = async (): Promise<CustomComponentDefinition | null> => {
    if (!api.createCustomComponent || !api.updateCustomComponent) return null;
    const payload = requestFromForm(form);
    if (!payload.display_name) throw new Error(zh ? "请填写组件名称。" : "Enter a component name.");
    const result = editingId
      ? await api.updateCustomComponent(projectId, editingId, payload)
      : await api.createCustomComponent(projectId, payload);
    setEditingId(result.component_id);
    setValidatedComponentId(null);
    await load();
    return result;
  };

  const runAction = async (action: "save" | "validate" | "publish") => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (action === "save") {
        const result = await saveDraft();
        if (result) setMessage(zh ? "草稿已保存；尚未进入可用版本。" : "Draft saved; it is not a published version.");
      } else if (action === "validate") {
        const saved = await saveDraft();
        if (!saved || !api.validateCustomComponent) return;
        const validated = await api.validateCustomComponent(projectId, saved.component_id);
        setForm(formFromDefinition(validated));
        setValidatedComponentId(saved.component_id);
        setMessage(`${zh ? "校验完成" : "Validation complete"}: ${readinessLabel(validated.readiness, zh)} · ${validated.reference}`);
        await load();
      } else {
        if (!editingId || validatedComponentId !== editingId || !api.publishCustomComponent) {
          throw new Error(zh ? "请先保存并成功校验草稿。" : "Save and successfully validate the draft first.");
        }
        const published = await api.publishCustomComponent(projectId, editingId);
        setEditingId(published.component_id);
        setValidatedComponentId(null);
        setForm(formFromDefinition(published));
        setMessage(`${zh ? "已发布不可变版本" : "Published immutable version"}: ${published.reference}`);
        await load();
        await onChanged?.();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "操作失败。" : "The operation failed."));
    } finally {
      setBusy(false);
    }
  };

  const deprecate = async (summary: CustomComponentSummary, version: string) => {
    if (!api.deprecateCustomComponent) return;
    const confirmed = window.confirm(zh
      ? `弃用 ${summary.slug}@${version}？已经固定该版本的 Agent 将无法继续使用它。`
      : `Deprecate ${summary.slug}@${version}? Agents pinned to this version will no longer be able to use it.`);
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.deprecateCustomComponent(projectId, summary.component_id, version);
      setMessage(`${zh ? "版本已弃用" : "Version deprecated"}: ${summary.slug}@${version}`);
      await load();
      await onChanged?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "弃用失败。" : "Deprecation failed."));
    } finally {
      setBusy(false);
    }
  };

  const deleteDraft = async (summary: CustomComponentSummary) => {
    if (!api.deleteCustomComponent || !summary.draft) return;
    const confirmed = window.confirm(zh ? `删除「${summary.display_name}」的草稿？已发布版本不会删除。` : `Delete the draft for “${summary.display_name}”? Published versions will remain.`);
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.deleteCustomComponent(projectId, summary.component_id);
      if (editingId === summary.component_id) startNew();
      setMessage(zh ? "草稿已删除；已发布版本保留。" : "Draft deleted; published versions remain.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "删除草稿失败。" : "Could not delete the draft."));
    } finally {
      setBusy(false);
    }
  };

  if (!api.listCustomComponents || !api.createCustomComponent || !api.updateCustomComponent) {
    return <Panel><SectionHeading eyebrow={zh ? "自定义组件" : "Custom Components"} title={zh ? "组件 API 尚未连接" : "Custom Component API is not connected"} detail={zh ? "当前 Desktop sidecar 没有提供完整的项目组件生命周期接口。" : "The current Desktop sidecar does not expose the full Project Component lifecycle API."} /></Panel>;
  }

  return (
    <Panel className="custom-components-panel">
      <div className="custom-components-header">
        <SectionHeading eyebrow={zh ? "项目能力" : "Project capabilities"} title={zh ? "自定义组件" : "Custom Components"} detail={zh ? "用声明式实现创建项目级复用能力。发布版本不可变；编辑只会生成草稿，不会自动升级已固定的 Agent。" : "Create reusable Project-owned capabilities with declarative implementations. Published versions are immutable; edits create drafts and never auto-upgrade pinned Agents."} />
        <Button variant="primary" disabled={interactionsDisabled} onClick={startNew}>{zh ? "新建组件" : "New component"}</Button>
      </div>
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {message ? <p className="custom-components-message" role="status">{message}</p> : null}
      <div className="custom-components-layout">
        <section className="custom-components-list" aria-label={zh ? "项目自定义组件" : "Project Custom Components"}>
          {loading ? <p>{zh ? "正在加载…" : "Loading…"}</p> : error ? (
            <EmptyState
              title={zh ? "组件列表不可用" : "Component list unavailable"}
              detail={zh ? "服务恢复并成功重试后，才能确认是否已有组件。" : "Retry after the local API is available to check whether components exist."}
            />
          ) : components.length ? components.map((component) => (
            <article className="custom-component-card" key={component.component_id}>
              <div className="custom-component-card-heading"><strong>{component.display_name}</strong><Tag>{component.slug}</Tag></div>
              <p>{component.description || (zh ? "无描述" : "No description")}</p>
              <small>{versionHint(component, zh)}</small>
              {component.versions.map((version) => (
                <div className="custom-component-version" key={version.reference}>
                  <span><code>{version.reference}</code><small>{version.implementation_kind} · {readinessLabel(version.readiness, zh)} · {version.lifecycle}</small></span>
                  {version.lifecycle === "active" ? <Button size="sm" variant="ghost" disabled={interactionsDisabled} onClick={() => void deprecate(component, version.version)}>{zh ? "弃用版本" : "Deprecate"}</Button> : <Tag>{zh ? "已弃用" : "Deprecated"}</Tag>}
                </div>
              ))}
              <div className="custom-component-card-actions">
                <Button size="sm" disabled={interactionsDisabled || !api.getCustomComponent} onClick={() => void edit(component)}>{zh ? (component.draft ? "编辑草稿" : "基于版本编辑") : (component.draft ? "Edit draft" : "Edit from version")}</Button>
                {component.draft ? <Button size="sm" variant="ghost" disabled={interactionsDisabled} onClick={() => void deleteDraft(component)}>{zh ? "删除草稿" : "Delete draft"}</Button> : null}
              </div>
            </article>
          )) : <EmptyState title={zh ? "还没有自定义组件" : "No Custom Components yet"} detail={zh ? "先创建草稿，再校验并发布一个不可变版本。" : "Create a draft, validate it, then publish an immutable version."} />}
        </section>
        <section className="custom-component-editor" aria-label={zh ? "组件草稿编辑器" : "Component draft editor"}>
          <h3>{editingId ? (zh ? "组件草稿" : "Component draft") : (zh ? "新组件草稿" : "New component draft")}</h3>
          <label>{zh ? "组件名称" : "Display name"}<input value={form.displayName} disabled={interactionsDisabled} onChange={(event) => updateForm({ displayName: event.target.value })} /></label>
          <label>{zh ? "描述" : "Description"}<textarea rows={2} value={form.description} disabled={interactionsDisabled} onChange={(event) => updateForm({ description: event.target.value })} /></label>
          <label>{zh ? "实现类型" : "Implementation kind"}<select value={form.implementationKind} disabled={interactionsDisabled} onChange={(event) => { const kind = event.target.value as CustomComponentImplementationKind; updateForm({ implementationKind: kind, implementation: implementationTemplates[kind] }); }}>{implementationKinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}</select></label>
          <label>{zh ? "输入字段 JSON" : "Inputs JSON"}<textarea className="custom-component-json" rows={4} spellCheck={false} value={form.inputs} disabled={interactionsDisabled} onChange={(event) => updateForm({ inputs: event.target.value })} /></label>
          <label>{zh ? "输出字段 JSON" : "Outputs JSON"}<textarea className="custom-component-json" rows={4} spellCheck={false} value={form.outputs} disabled={interactionsDisabled} onChange={(event) => updateForm({ outputs: event.target.value })} /></label>
          <label>{zh ? "实现配置 JSON（不含 kind）" : "Implementation config JSON (without kind)"}<textarea className="custom-component-json" rows={6} spellCheck={false} value={form.implementation} disabled={interactionsDisabled} onChange={(event) => updateForm({ implementation: event.target.value })} /></label>
          <label>{zh ? "元数据 JSON（仅字符串）" : "Metadata JSON (strings only)"}<textarea className="custom-component-json" rows={3} spellCheck={false} value={form.metadata} disabled={interactionsDisabled} onChange={(event) => updateForm({ metadata: event.target.value })} /></label>
          <p className="custom-component-safety-note">{zh ? "这里只接受声明式实现，不执行任意代码。依赖、权限和运行就绪度由后端核对；前端表单不会授权权限。" : "Only declarative implementations are accepted; arbitrary code is not executed. Dependencies, permissions, and runtime readiness are checked by the backend; this form does not grant permissions."}</p>
          <div className="custom-component-editor-actions">
            <Button disabled={interactionsDisabled} onClick={() => void runAction("save")}>{zh ? "保存草稿" : "Save draft"}</Button>
            <Button disabled={interactionsDisabled || !editingId || !api.validateCustomComponent} onClick={() => void runAction("validate")}>{zh ? "校验" : "Validate"}</Button>
            <Button variant="primary" disabled={interactionsDisabled || !editingId || validatedComponentId !== editingId || !api.publishCustomComponent} onClick={() => void runAction("publish")}>{zh ? "发布版本" : "Publish version"}</Button>
          </div>
        </section>
      </div>
    </Panel>
  );
}
