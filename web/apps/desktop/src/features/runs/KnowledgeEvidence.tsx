import { useState } from "react";
import { projectRoutePaths, type KnowledgeRetrievalHit, type RuntimeEvent } from "@veyra/api-contracts";
import { Button, LinkButton } from "@veyra/ui";
import { LocalApiClientError, type LocalProjectApi } from "../../api/local-client";
import { knowledgeEvidence } from "./knowledge-evidence";

function knowledgeIdFromReference(reference: string): string {
  const separator = reference.lastIndexOf("@");
  return separator === -1 ? reference : reference.slice(0, separator);
}

function KnowledgeHit({ hit, api, projectId, zh }: {
  hit: KnowledgeRetrievalHit;
  api?: LocalProjectApi;
  projectId: string;
  zh: boolean;
}) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const knowledgeId = knowledgeIdFromReference(hit.reference);

  const preview = async () => {
    if (busy) return;
    if (open) {
      setOpen(false);
      setText(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (!api?.getKnowledgeChunk) throw new Error("unavailable");
      const excerpt = await api.getKnowledgeChunk(
        projectId,
        knowledgeId,
        hit.chunk_id,
        hit.source_file_hash,
      );
      if (
        excerpt.project_id !== projectId
        || excerpt.reference !== hit.reference
        || excerpt.source_file_hash !== hit.source_file_hash
        || excerpt.chunk_id !== hit.chunk_id
        || excerpt.line_start !== hit.line_start
        || excerpt.line_end !== hit.line_end
        || [...excerpt.text].length > 2000
      ) {
        throw new Error("identity mismatch");
      }
      setText(excerpt.text);
      setOpen(true);
    } catch (cause) {
      const changed = cause instanceof LocalApiClientError && ["knowledge_source_mismatch", "knowledge_index_stale"].includes(cause.code ?? "");
      setError(changed
        ? (zh ? "该历史来源内容已变化，无法再预览原片段。" : "Historical source changed; the original excerpt is unavailable.")
        : (zh ? "该历史来源无法读取，无法预览原片段。" : "Historical source unavailable; the original excerpt cannot be previewed."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="knowledge-hit">
      <h4>
        <LinkButton href={projectRoutePaths.knowledgeItem(projectId, knowledgeId)}>
          {hit.reference}
        </LinkButton>
      </h4>
      <p>
        {zh ? "片段索引" : "Chunk index"} {hit.chunk_index}
        {" · "}
        {zh ? "行" : "Lines"} {hit.line_start}–{hit.line_end}
        {" · "}Rank {hit.rank}
        {" · "}Score {hit.score}
      </p>
      <p>
        {zh ? "使用的来源 hash" : "Used source hash"}
        {": "}
        <code title={hit.source_file_hash}>{hit.source_file_hash.slice(0, 12)}</code>
      </p>
      <details>
        <summary>{zh ? "片段身份" : "Chunk identity"}</summary>
        <code>{hit.chunk_id}</code>
        <p><code>{hit.source_file_hash}</code></p>
      </details>
      <Button disabled={busy} onClick={() => void preview()}>
        {busy
          ? (zh ? "正在读取…" : "Loading excerpt…")
          : open
            ? (zh ? "收起片段" : "Collapse excerpt")
            : (zh ? "展开片段" : "Expand excerpt")}
      </Button>
      {error ? <p role="status">{error}</p> : null}
      {open && text !== null ? <pre><code>{text}</code></pre> : null}
    </li>
  );
}

export function KnowledgeEvidence({
  events,
  api,
  projectId,
  locale,
}: {
  events: RuntimeEvent[];
  api?: LocalProjectApi;
  projectId: string;
  locale: "zh" | "en";
}) {
  const retrievals = events.flatMap((event) => {
    const evidence = knowledgeEvidence(event);
    return evidence ? [{ event, evidence }] : [];
  });
  if (!retrievals.length) return null;
  const zh = locale === "zh";
  return (
    <section className="knowledge-evidence" aria-label={zh ? "Knowledge 检索证据" : "Knowledge Evidence"}>
      <h3>{zh ? "Knowledge 检索证据" : "Knowledge Evidence"}</h3>
      <p>
        {zh
          ? "本次运行检索并加入上下文的真实片段；不是逐句引用归因。来源链接打开当前资料。"
          : "Chunks retrieved into this Run’s context, not sentence-level attribution. Source links open the current document."}
      </p>
      {retrievals.map(({ event, evidence }) => (
        <div className="knowledge-evidence-run" key={event.event_id}>
          <p>
            Query hash: <code title={evidence.query_hash}>{evidence.query_hash.slice(0, 12)}</code>
            {" · "}
            {evidence.hit_count} {zh ? "个片段" : "chunks"}
          </p>
          {!evidence.hit_count
            ? <p>{zh ? "未检索到相关 Knowledge 片段。" : "No relevant Knowledge chunks retrieved."}</p>
            : null}
          <ol className="studio-event-list">
            {evidence.receipts.map((hit) => (
              <KnowledgeHit
                key={`${event.event_id}:${hit.source_file_hash}:${hit.chunk_id}:${hit.rank}`}
                hit={hit}
                api={api}
                projectId={projectId}
                zh={zh}
              />
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}
