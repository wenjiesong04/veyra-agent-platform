import * as React from "react";
import { Eye, FileText, Upload, X } from "lucide-react";
import {
  acceptedMediaTypes,
  compactFieldType,
  fieldIsMultiple,
  fieldIsRequired,
  isArtifactCollection,
  isArtifactCompactType,
  isArtifactRef,
  type ArtifactCollection,
  type ArtifactRecord,
  type ArtifactRef,
  type JsonValue,
  type TypedFieldSpec,
  type TypedFields,
} from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";

type Locale = "zh" | "en";

const copy = {
  zh: {
    empty: "此 Agent 不需要输入。",
    upload: "上传",
    uploading: "正在上传…",
    remove: "移除",
    multiple: "可上传多个文件",
    required: "必填",
    optional: "可选",
    fileHelp: {
      image: "上传图片，可在运行结果中预览。",
      pdf: "上传 PDF 文件。",
      document: "上传支持的文档，例如 PDF 或 DOCX。",
      file: "上传此 Agent 接受的文件。",
      audio: "上传音频文件。",
      video: "上传视频文件。",
      collection: "添加一个或多个文件。",
    },
    failed: "上传失败",
    missingApi: "当前界面不能上传 Artifact。",
  },
  en: {
    empty: "This Agent has no inputs.",
    upload: "Upload",
    uploading: "Uploading…",
    remove: "Remove",
    multiple: "Multiple files allowed",
    required: "Required",
    optional: "Optional",
    fileHelp: {
      image: "Upload images. Previews appear with the run results.",
      pdf: "Upload a PDF file.",
      document: "Upload a supported document, such as PDF or DOCX.",
      file: "Upload a file accepted by this Agent.",
      audio: "Upload an audio file.",
      video: "Upload a video file.",
      collection: "Add one or more files.",
    },
    failed: "Upload failed",
    missingApi: "Artifact upload is not available here.",
  },
} as const;

function inputTypeLabel(type: string, locale: Locale): string {
  const labels: Record<string, { zh: string; en: string }> = {
    string: { zh: "文本", en: "Text" },
    number: { zh: "数字", en: "Number" },
    integer: { zh: "整数", en: "Integer" },
    boolean: { zh: "开关", en: "Yes / no" },
    object: { zh: "JSON 对象", en: "JSON object" },
    array: { zh: "列表", en: "List" },
    table: { zh: "表格", en: "Table" },
    image: { zh: "图片", en: "Image" },
    pdf: { zh: "PDF", en: "PDF" },
    document: { zh: "文档", en: "Document" },
    file: { zh: "文件", en: "File" },
    audio: { zh: "音频", en: "Audio" },
    video: { zh: "视频", en: "Video" },
    collection: { zh: "文件集合", en: "File collection" },
  };
  return labels[type]?.[locale] ?? type;
}

export function initialRuntimeValues(schema: TypedFields): Record<string, JsonValue> {
  return Object.fromEntries(Object.entries(schema).flatMap(([name, spec]) => {
    const type = compactFieldType(spec);
    if (isArtifactCompactType(type)) return [];
    return [[name, type === "boolean" ? false : type === "integer" || type === "number" ? 0 : type === "object" ? {} : type === "array" || type === "table" ? [] : ""]];
  }));
}

export function requiredArtifactsReady(schema: TypedFields, values: Record<string, JsonValue>): boolean {
  return Object.entries(schema).every(([name, spec]) => {
    const type = compactFieldType(spec);
    if (!isArtifactCompactType(type)) return true;
    if (typeof spec !== "string" && spec.required === false) return true;
    const value = values[name];
    if (type === "collection") return isArtifactCollection(value) && value.items.length > 0;
    if (fieldIsMultiple(spec)) return Array.isArray(value) && value.length > 0 && value.every(isArtifactRef);
    return isArtifactRef(value);
  });
}

function toRef(record: ArtifactRecord): ArtifactRef {
  return {
    kind: "artifact",
    artifact_id: record.artifact_id,
    media_type: record.media_type,
    filename: record.filename,
  };
}

function refsOf(value: JsonValue | undefined, multiple: boolean): ArtifactRef[] {
  if (multiple) {
    return Array.isArray(value) ? value.filter(isArtifactRef) : [];
  }
  return isArtifactRef(value) ? [value] : [];
}

export function RuntimeInputForm({
  schema,
  values,
  onChange,
  emptyLabel,
  fileOptions = [],
  locale = "en",
  projectId,
  api,
  presentation = "default",
}: {
  schema: TypedFields;
  values: Record<string, JsonValue>;
  onChange: (values: Record<string, JsonValue>) => void;
  emptyLabel?: string;
  fileOptions?: string[];
  locale?: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "uploadArtifact" | "artifactContent">;
  presentation?: "default" | "workspace";
}) {
  const text = copy[locale];
  const entries = Object.entries(schema);
  return (
    <>
      {entries.map(([name, spec]) => (
        <RuntimeInputField
          key={name}
          name={name}
          spec={spec}
          value={values[name]}
          values={values}
          onChange={onChange}
          fileOptions={fileOptions}
          locale={locale}
          projectId={projectId}
          api={api}
          presentation={presentation}
        />
      ))}
      {!entries.length ? <p>{emptyLabel ?? text.empty}</p> : null}
    </>
  );
}

function RuntimeInputField({
  name,
  spec,
  value,
  values,
  onChange,
  fileOptions,
  locale,
  projectId,
  api,
  presentation,
}: {
  name: string;
  spec: TypedFieldSpec;
  value: JsonValue | undefined;
  values: Record<string, JsonValue>;
  onChange: (values: Record<string, JsonValue>) => void;
  fileOptions: string[];
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "uploadArtifact" | "artifactContent">;
  presentation: "default" | "workspace";
}) {
  const inputId = React.useId();
  const type = compactFieldType(spec);
  const text = copy[locale];
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const multiple = fieldIsMultiple(spec);
  const accept = acceptedMediaTypes(spec).join(",");
  const listId = type === "string" && fileOptions.length > 0 && /(^|_)(path|file|document)(_|$)/i.test(name)
    ? `run-file-options-${name}`
    : undefined;
  const description = typeof spec === "string" ? "" : spec.description?.trim() ?? "";
  const typeLabel = inputTypeLabel(type, locale);
  const workspace = presentation === "workspace";
  const refs = type === "collection" && isArtifactCollection(value) ? value.items : refsOf(value, multiple);

  const setValue = (next: JsonValue | undefined) => {
    if (next === undefined) {
      const rest = { ...values };
      delete rest[name];
      onChange(rest);
      return;
    }
    onChange({ ...values, [name]: next });
  };

  const uploadFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    if (!api?.uploadArtifact || !projectId) {
      setError(text.missingApi);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const uploaded: ArtifactRef[] = [];
      for (const file of Array.from(files)) {
        uploaded.push(toRef(await api.uploadArtifact(projectId, file)));
      }
      if (multiple) {
        setValue([...refsOf(value, true), ...uploaded]);
      } else if (type === "collection") {
        const existing = isArtifactCollection(value) ? value.items : [];
        const next: ArtifactCollection = {
          kind: "collection",
          collection_id: isArtifactCollection(value) ? value.collection_id : crypto.randomUUID(),
          items: [...existing, ...uploaded],
        };
        setValue(next);
      } else {
        setValue(uploaded[0]);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : text.failed);
    } finally {
      setBusy(false);
    }
  };

  const removeAt = (index: number) => {
    if (multiple) {
      const next = refsOf(value, true).filter((_, item) => item !== index);
      setValue(next.length ? next : undefined);
      return;
    }
    if (type === "collection" && isArtifactCollection(value)) {
      const items = value.items.filter((_, item) => item !== index);
      setValue(items.length ? { ...value, items } : undefined);
      return;
    }
    setValue(undefined);
  };

  return (
    <div className={`runtime-input-field${workspace ? " is-workspace" : ""}`} data-field-type={type}>
      <label className="runtime-input-field-head" htmlFor={inputId}>
        <strong className="runtime-input-field-name">{name}</strong>
        <span className="runtime-input-field-meta">
          <small className="runtime-input-type">{typeLabel}</small>
          <small className={`runtime-input-requirement${fieldIsRequired(spec) ? " is-required" : ""}`}>
            {fieldIsRequired(spec) ? text.required : text.optional}
          </small>
        </span>
      </label>
      {description ? <small className="runtime-input-description">{description}</small> : null}
      {type === "boolean" ? (
        <select
          id={inputId}
          name={name}
          aria-label={name}
          value={String(value ?? false)}
          onChange={(event) => setValue(event.target.value === "true")}
        >
          <option value="false">false</option>
          <option value="true">true</option>
        </select>
      ) : type === "object" || type === "array" || type === "table" ? (
        <textarea
          id={inputId}
          name={name}
          autoComplete="off"
          rows={3}
          aria-label={name}
          value={typeof value === "string" ? String(value) : JSON.stringify(value ?? (type === "object" ? {} : []), null, 2)}
          onChange={(event) => {
            try {
              const parsed: unknown = JSON.parse(event.target.value);
              if (type === "object" ? Boolean(parsed) && typeof parsed === "object" && !Array.isArray(parsed) : Array.isArray(parsed)) {
                setValue(parsed as JsonValue);
                return;
              }
            } catch {
              // Keep typing until JSON is valid.
            }
            setValue(event.target.value);
          }}
        />
      ) : isArtifactCompactType(type) ? (
        <div className="runtime-artifact-input">
          {!workspace || !description ? <small className="runtime-input-file-help">{text.fileHelp[type]}</small> : null}
          <input
            id={inputId}
            name={name}
            className={workspace ? "runtime-file-native" : undefined}
            type="file"
            aria-label={name}
            accept={accept || undefined}
            multiple={multiple || type === "collection"}
            disabled={busy}
            onChange={(event) => {
              void uploadFiles(event.target.files);
              event.currentTarget.value = "";
            }}
          />
          {workspace ? <label className={`runtime-file-picker${busy ? " is-busy" : ""}`} htmlFor={inputId}>
            <Upload size={16} aria-hidden="true" />
            {busy ? text.uploading : refs.length && !multiple && type !== "collection" ? (locale === "zh" ? "更换文件" : "Replace file") : (locale === "zh" ? "选择文件" : "Choose file")}
          </label> : null}
          {busy ? <small role="status">{text.uploading}</small> : null}
          {multiple || type === "collection" ? <small className="runtime-input-multiple">{text.multiple}</small> : null}
          <ArtifactPreviewList
            refs={refs}
            locale={locale}
            projectId={projectId}
            api={api}
            onRemove={removeAt}
            compact={workspace}
          />
          {error ? <small className="runtime-io-error" role="alert">{error}</small> : null}
        </div>
      ) : type === "string" && !listId ? (
        <textarea
          id={inputId}
          name={name}
          autoComplete="off"
          rows={3}
          aria-label={name}
          value={String(value ?? "")}
          onChange={(event) => setValue(event.target.value)}
        />
      ) : (
        <>
          <input
            id={inputId}
            name={name}
            autoComplete="off"
            type={type === "integer" || type === "number" ? "number" : "text"}
            step={type === "integer" ? "1" : "any"}
            list={listId}
            aria-label={name}
            value={String(value ?? "")}
            onChange={(event) => {
              const next: JsonValue = type === "integer"
                ? Number.parseInt(event.target.value || "0", 10)
                : type === "number"
                  ? Number.parseFloat(event.target.value || "0")
                  : event.target.value;
              setValue(next);
            }}
          />
          {listId ? <datalist id={listId}>{fileOptions.slice(0, 100).map((path) => <option value={path} key={path} />)}</datalist> : null}
        </>
      )}
    </div>
  );
}

function ArtifactPreviewList({
  refs,
  locale,
  projectId,
  api,
  onRemove,
  compact = false,
}: {
  refs: ArtifactRef[];
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
  onRemove: (index: number) => void;
  compact?: boolean;
}) {
  const text = copy[locale];
  if (!refs.length) return null;
  return (
    <ul className="runtime-artifact-list">
      {refs.map((item, index) => (
        <li key={`${item.artifact_id}:${index}`}>
          <ArtifactCard item={item} locale={locale} projectId={projectId} api={api} compact={compact} />
          <button type="button" aria-label={compact ? `${text.remove} ${item.filename}` : undefined} title={compact ? `${text.remove} ${item.filename}` : undefined} onClick={() => onRemove(index)}>{compact ? <X size={16} aria-hidden="true" /> : text.remove}</button>
        </li>
      ))}
    </ul>
  );
}

async function previewUrlFor(blob: Blob): Promise<string> {
  if (typeof URL.createObjectURL === "function") {
    try {
      const url = URL.createObjectURL(blob);
      if (url) return url;
    } catch {
      // Fall through to a data URL so image previews still render in tests and older browsers.
    }
  }
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("The image preview could not be created."));
    reader.readAsDataURL(blob);
  });
}

export function ArtifactCard({
  item,
  locale,
  projectId,
  api,
  compact = false,
}: {
  item: ArtifactRef;
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
  compact?: boolean;
}) {
  const zh = locale === "zh";
  const [url, setUrl] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!api?.artifactContent || !projectId || !item.media_type.startsWith("image/")) {
      setUrl(null);
      return;
    }
    let current = true;
    let objectUrl = "";
    void api.artifactContent(projectId, item.artifact_id).then(async (blob) => {
      const preview = await previewUrlFor(blob);
      if (preview.startsWith("blob:")) objectUrl = preview;
      if (!current) {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        return;
      }
      setUrl(preview);
    }).catch(() => {
      if (current) setUrl(null);
    });
    return () => {
      current = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, projectId, item.artifact_id, item.media_type]);

  const open = async () => {
    if (!api?.artifactContent || !projectId) return;
    const blob = await api.artifactContent(projectId, item.artifact_id);
    const href = URL.createObjectURL(blob);
    window.open(href, "_blank", "noopener,noreferrer");
  };

  return (
    <div className={`runtime-artifact-card${compact ? " is-compact" : ""}`}>
      {compact && !item.media_type.startsWith("image/") ? <FileText size={18} aria-hidden="true" /> : null}
      {item.media_type.startsWith("image/") && url ? <img src={url} alt={item.filename} /> : null}
      <strong>{item.filename}</strong>
      <small>{item.media_type}</small>
      {api?.artifactContent && projectId ? (
        <button type="button" aria-label={compact ? `${zh ? "查看" : "Open"} ${item.filename}` : undefined} title={compact ? `${zh ? "查看" : "Open"} ${item.filename}` : undefined} onClick={() => void open()}>{compact ? <Eye size={16} aria-hidden="true" /> : zh ? "查看" : "Open"}</button>
      ) : null}
    </div>
  );
}
