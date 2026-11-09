import { describe, expect, it, vi } from "vitest";
import { LocalApiClient } from "./local-client";

const processing = { origin: "upload", filename: "thesis.txt", media_type: "text/plain", uploaded_content_hash: "a".repeat(64), content_hash: "a".repeat(64), ingest_status: "ingested", parse_status: "parsed", index_status: "not_indexed", failure_reason: null, updated_at: "2026-09-15T00:00:00Z" };
const document = { schema_version: "1.0", project_id: "project-1", knowledge_id: "knowledge-1", slug: "thesis", name: "Thesis", description: "", version: "1.0.0", source_path: "knowledge/thesis/document.md", source_file_hash: "a".repeat(64), text: "Thesis", processing };

describe("Knowledge ingest wire", () => {
  it.each(["not_indexed", "indexed", "stale", "failed"])("preserves %s index truth and calls explicit POST", async (index_status) => {
    const indexed = { ...document, processing: { ...processing, index_status, chunk_count: index_status === "indexed" || index_status === "stale" ? 2 : null, failure_reason: index_status === "stale" ? "Content changed; rebuild" : null } };
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(indexed)));
    const api = new LocalApiClient({ fetcher });
    await expect(api.buildKnowledgeIndex("project-1", "knowledge-1")).resolves.toEqual(indexed);
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/knowledge/knowledge-1/index");
    expect(fetcher.mock.calls[0]?.[1].method).toBe("POST");
    await expect(api.getKnowledge("project-1", "knowledge-1")).resolves.toEqual(indexed);
  });

  it.each([{ index_status: "indexing" }, { chunk_count: -1 }, { chunk_count: 1.5 }])("rejects invalid index facts %j", async (invalid) => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...document, processing: { ...processing, ...invalid } })));
    await expect(new LocalApiClient({ fetcher }).getKnowledge("p", "k")).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("preserves a typed build failure", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "knowledge_index_too_large", message: "Index too large" }), { status: 422 }));
    await expect(new LocalApiClient({ fetcher }).buildKnowledgeIndex("p", "k")).rejects.toMatchObject({ code: "knowledge_index_too_large" });
  });

  it("uploads multipart and preserves backend facts on upload and reload", async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(document)));
    const api = new LocalApiClient({ fetcher });
    const file = new File(["Thesis"], "thesis.txt");
    await expect(api.ingestKnowledge("project-1", file)).resolves.toEqual(document);
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/projects/project-1/knowledge/ingest");
    expect(fetcher.mock.calls[0]?.[1].body.get("file")).toBe(file);
    await expect(api.getKnowledge("project-1", "knowledge-1")).resolves.toEqual(document);
  });

  it("retains typed backend failure without manufacturing an ingested source", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ schema_version: "1.0", code: "knowledge_parse_failed", message: "Knowledge upload must be UTF-8 text" }), { status: 422 }));
    const api = new LocalApiClient({ fetcher });
    await expect(api.ingestKnowledge("project-1", new File(["bad"], "thesis.txt"))).rejects.toMatchObject({ code: "knowledge_parse_failed", status: 422 });
  });
});
