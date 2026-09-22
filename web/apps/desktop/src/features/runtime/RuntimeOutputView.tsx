import { isArtifactRef, type ArtifactRef, type JsonValue } from "@veyra/api-contracts";
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
    return (
      <ul className="runtime-artifact-grid">
        {result.map((item, index) => (
          <li key={`${item.artifact_id}:${index}`}>
            <ArtifactCard item={item} locale={locale} projectId={projectId} api={api} />
          </li>
        ))}
      </ul>
    );
  }
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
    return (
      <ul className="runtime-artifact-grid">
        {value.map((item: ArtifactRef, index) => (
          <li key={`${item.artifact_id}:${index}`}>
            <ArtifactCard item={item} locale={locale} projectId={projectId} api={api} />
          </li>
        ))}
      </ul>
    );
  }
  return <pre><code>{JSON.stringify(value, null, 2)}</code></pre>;
}
