import * as React from "react";
import type { EvaluationFinding } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";

export function ReviewArtifactPreview({ api, projectId, evidence, locale }: { api: LocalProjectApi; projectId: string; evidence: EvaluationFinding["evidence"][number]; locale: "zh" | "en" }) {
  const [url, setUrl] = React.useState("");
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    let ownedUrl = "";
    setUrl(""); setError("");
    void (async () => {
      if (!api.artifactContent) return;
      try {
        const blob = await api.artifactContent(projectId, evidence.artifact_id);
        if (!live) return;
        if (blob.size !== evidence.size_bytes) throw new Error("snapshot");
        const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
        if (Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("") !== evidence.sha256) throw new Error("snapshot");
        if (!["image/png", "image/jpeg", "image/webp", "image/gif"].includes(blob.type)) throw new Error("unsupported");
        if (live) { ownedUrl = URL.createObjectURL(blob); setUrl(ownedUrl); }
      } catch (cause) {
        if (live) setError(cause instanceof Error && cause.message === "snapshot" ? (locale === "zh" ? "文件内容与该报告快照不一致，请重新验收。" : "File contents differ from this report snapshot. Create a new evaluation.") : (locale === "zh" ? "此产物无法安全预览。" : "This artifact cannot be safely previewed."));
      }
    })();
    return () => { live = false; if (ownedUrl) URL.revokeObjectURL(ownedUrl); };
  }, [api, projectId, evidence.artifact_id, evidence.sha256, evidence.size_bytes, locale]);
  return <figure className="run-review-preview">
    {url ? <img src={url} alt={evidence.artifact_id} /> : <p role="status">{error || (locale === "zh" ? "正在核对图片快照…" : "Checking image snapshot…")}</p>}
    <figcaption><code>{evidence.artifact_id}</code></figcaption>
  </figure>;
}
