import type { ProjectKnowledgeRecord, SaveDraftResponse } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";

export async function bindKnowledgeToAgent(
  api: LocalProjectApi,
  projectId: string,
  agentId: string,
  knowledge: ProjectKnowledgeRecord,
): Promise<SaveDraftResponse> {
  if (!api.saveDraft) throw new Error("This workspace cannot update Agent context.");
  const draft = await api.getDraft(projectId, agentId);
  const reference = `${knowledge.knowledge_id}@${knowledge.version ?? "1.0.0"}`;
  const knowledgePrefix = `${knowledge.knowledge_id}@`;
  const previous = Object.entries(draft.source.ui.bindings ?? {}).find(([, binding]) => binding.kind === "knowledge" && binding.reference.startsWith(knowledgePrefix));
  const bindings = Object.fromEntries(Object.entries(draft.source.ui.bindings ?? {}).filter(([, binding]) => !(binding.kind === "knowledge" && binding.reference.startsWith(knowledgePrefix))));
  const bindingId = previous?.[0] ?? nextBindingId(bindings, knowledge.knowledge_id);
  const position = previous?.[1] ?? {
    kind: "knowledge" as const,
    reference,
    x: 24 + (Object.keys(bindings).length % 3) * 220,
    y: 24 + Math.floor(Object.keys(bindings).length / 3) * 140,
  };
  const source = {
    ...draft.source,
    extensions: {
      ...draft.source.extensions,
      veyra: {
        ...draft.source.extensions.veyra,
        knowledge_refs: [...new Set([
          ...(draft.source.extensions.veyra.knowledge_refs ?? []).filter((item) => !item.startsWith(knowledgePrefix)),
          reference,
        ])],
      },
    },
    ui: {
      ...draft.source.ui,
      bindings: { ...bindings, [bindingId]: { ...position, reference } },
    },
    lock: {
      ...Object.fromEntries(Object.entries(draft.source.lock).filter(([item]) => !item.startsWith(knowledgePrefix))),
      [reference]: knowledge.source_file_hash,
    },
  };
  return api.saveDraft(
    projectId,
    agentId,
    { source, expected_revision: draft.revision },
    { etag: draft.etag },
  );
}

function nextBindingId(bindings: Record<string, unknown>, knowledgeId: string): string {
  const base = `knowledge_${knowledgeId.replace(/[^a-z0-9]/gi, "").slice(0, 12) || "context"}`;
  if (!bindings[base]) return base;
  let index = 2;
  while (bindings[`${base}_${index}`]) index += 1;
  return `${base}_${index}`;
}
