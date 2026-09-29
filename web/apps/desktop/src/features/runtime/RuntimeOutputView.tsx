import { isArtifactRef, type ArtifactRef, type JsonObject, type JsonValue } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { ArtifactCard } from "./RuntimeInputForm";

type Locale = "zh" | "en";

export function RuntimeOutputView({
  result,
  locale,
  projectId,
  api,
}: {
  result: JsonValue | null | undefined;
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
}) {
  if (result == null) return null;
  if (isArtifactRef(result)) {
    return <ArtifactCard item={result} locale={locale} projectId={projectId} api={api} />;
  }
  if (Array.isArray(result) && result.length > 0 && result.every(isArtifactRef)) {
    return <ArtifactList items={result} locale={locale} projectId={projectId} api={api} />;
  }
  const rows = objectRows(result);
  if (rows) return <RuntimeTable rows={rows} locale={locale} projectId={projectId} api={api} />;
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const entries = Object.entries(result);
    if (!entries.length) return <pre><code>{"{}"}</code></pre>;
    return (
      <dl className="runtime-output-fields">
        {entries.map(([name, value]) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd><RuntimeValueView value={value} locale={locale} projectId={projectId} api={api} /></dd>
          </div>
        ))}
      </dl>
    );
  }
  return <RuntimeValueView value={result} locale={locale} projectId={projectId} api={api} />;
}

function RuntimeValueView({
  value,
  locale,
  projectId,
  api,
}: {
  value: JsonValue;
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
}) {
  if (typeof value === "string") {
    return <pre className="runtime-output-text"><code>{value}</code></pre>;
  }
  if (typeof value === "number" || typeof value === "boolean" || value === null) {
    return <p className="runtime-output-scalar">{String(value)}</p>;
  }
  if (isArtifactRef(value)) {
    return <ArtifactCard item={value} locale={locale} projectId={projectId} api={api} />;
  }
  if (Array.isArray(value) && value.length > 0 && value.every(isArtifactRef)) {
    return <ArtifactList items={value} locale={locale} projectId={projectId} api={api} />;
  }
  const rows = objectRows(value);
  if (rows) return <RuntimeTable rows={rows} locale={locale} projectId={projectId} api={api} />;
  return <pre><code>{JSON.stringify(value, null, 2)}</code></pre>;
}

function ArtifactList({
  items,
  locale,
  projectId,
  api,
}: {
  items: ArtifactRef[];
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
}) {
  return (
    <ul className="runtime-artifact-grid">
      {items.map((item, index) => (
        <li key={`${item.artifact_id}:${index}`}>
          <ArtifactCard item={item} locale={locale} projectId={projectId} api={api} />
        </li>
      ))}
    </ul>
  );
}

function objectRows(value: JsonValue): JsonObject[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  if (!value.every((item) => item && typeof item === "object" && !Array.isArray(item) && !isArtifactRef(item))) return null;
  return value as JsonObject[];
}

function RuntimeTable({
  rows,
  locale,
  projectId,
  api,
}: {
  rows: JsonObject[];
  locale: Locale;
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
}) {
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <div className="runtime-output-table-wrap">
      <table className="runtime-output-table">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>
                  {row[column] === undefined ? "" : (
                    <RuntimeValueView value={row[column] as JsonValue} locale={locale} projectId={projectId} api={api} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
