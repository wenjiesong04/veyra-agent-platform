import * as React from "react";
import {
  acceptedMediaTypes,
  compactFieldType,
  fieldIsMultiple,
  isArtifactCompactType,
  isArtifactRef,
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
    failed: "上传失败",
    missingApi: "当前界面不能上传 Artifact。",
  },
  en: {
    empty: "This Agent has no inputs.",
    upload: "Upload",
    uploading: "Uploading…",
    remove: "Remove",
    multiple: "Multiple files allowed",
    failed: "Upload failed",
    missingApi: "Artifact upload is not available here.",
  },
} as const;

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
}: {
  schema: TypedFields;
  values: Record<string, JsonValue>;
  onChange: (values: Record<string, JsonValue>) => void;
  emptyLabel?: string;
  fileOptions?: string[];
  locale?: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "uploadArtifact" | "artifactContent">;
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
}) {
  const type = compactFieldType(spec);
  const text = copy[locale];
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const multiple = fieldIsMultiple(spec);
  const accept = acceptedMediaTypes(spec).join(",");
  const listId = type === "string" && fileOptions.length > 0 && /(^|_)(path|file|document)(_|$)/i.test(name)
    ? `run-file-options-${name}`
    : undefined;

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
    setValue(undefined);
  };

  return (
    <label>
      <span>{name}<small>{type}{multiple ? "[]" : ""}</small></span>
      {type === "boolean" ? (
        <select
          aria-label={name}
          value={String(value ?? false)}
          onChange={(event) => setValue(event.target.value === "true")}
        >
          <option value="false">false</option>
          <option value="true">true</option>
        </select>
      ) : type === "object" || type === "array" || type === "table" ? (
        <textarea
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
          <input
            type="file"
            aria-label={name}
            accept={accept || undefined}
            multiple={multiple}
            disabled={busy}
            onChange={(event) => {
              void uploadFiles(event.target.files);
              event.currentTarget.value = "";
            }}
          />
          {busy ? <small>{text.uploading}</small> : null}
          {multiple ? <small>{text.multiple}</small> : null}
          <ArtifactPreviewList
            refs={refsOf(value, multiple)}
            locale={locale}
            projectId={projectId}
            api={api}
            onRemove={removeAt}
          />
          {error ? <small className="runtime-io-error">{error}</small> : null}
        </div>
      ) : (
        <>
          <input
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
    </label>
  );
}

function ArtifactPreviewList({
  refs,
  locale,
  projectId,
  api,
  onRemove,
}: {
  refs: ArtifactRef[];
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
  onRemove: (index: number) => void;
}) {
  const text = copy[locale];
  if (!refs.length) return null;
  return (
    <ul className="runtime-artifact-list">
      {refs.map((item, index) => (
        <li key={`${item.artifact_id}:${index}`}>
          <ArtifactCard item={item} locale={locale} projectId={projectId} api={api} />
          <button type="button" onClick={() => onRemove(index)}>{text.remove}</button>
        </li>
      ))}
    </ul>
  );
}

export function ArtifactCard({
  item,
  locale,
  projectId,
  api,
}: {
  item: ArtifactRef;
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
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
    void api.artifactContent(projectId, item.artifact_id).then((blob) => {
      objectUrl = URL.createObjectURL(blob);
      if (!current) {
        URL.revokeObjectURL(objectUrl);
        return;
      }
      setUrl(objectUrl);
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
    <div className="runtime-artifact-card">
      {item.media_type.startsWith("image/") && url ? <img src={url} alt={item.filename} /> : null}
      <strong>{item.filename}</strong>
      <small>{item.media_type}</small>
      {api?.artifactContent && projectId ? (
        <button type="button" onClick={() => void open()}>{zh ? "查看" : "Open"}</button>
      ) : null}
    </div>
  );
}
