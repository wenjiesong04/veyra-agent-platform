import type { KnowledgeRetrievalEvidence, KnowledgeRetrievalHit, RuntimeEvent } from "@veyra/api-contracts";

const hash = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const integer = (value: unknown, minimum: number): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= minimum;

export function knowledgeEvidence(event: RuntimeEvent): KnowledgeRetrievalEvidence | null {
  const payload = event.payload;
  if (event.kind !== "tool.completed" || payload.tool_reference !== "knowledge.context"
    || !hash(payload.query_hash) || !integer(payload.hit_count, 0) || !Array.isArray(payload.receipts)
    || payload.hit_count !== payload.receipts.length) return null;
  const receipts: KnowledgeRetrievalHit[] = [];
  for (const value of payload.receipts) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const { reference, source_file_hash, chunk_id, chunk_index, line_start, line_end, rank, score } = value;
    if (typeof reference !== "string" || !/^[0-9a-f-]{36}@[^/@\s]+$/.test(reference)
      || !hash(source_file_hash) || !hash(chunk_id) || !integer(chunk_index, 0)
      || !integer(line_start, 1) || !integer(line_end, line_start) || !integer(rank, 1)
      || typeof score !== "number" || !Number.isFinite(score) || score <= 0) return null;
    receipts.push({ reference, source_file_hash, chunk_id, chunk_index, line_start, line_end, rank, score });
  }
  return { query_hash: payload.query_hash, hit_count: payload.hit_count, receipts };
}
