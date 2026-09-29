import { compactFieldType, isArtifactCompactType, type AgentSource, type TypedFields } from "@veyra/api-contracts";

export type InteractionMode = "auto" | "chat" | "form" | "hybrid";
export type ResolvedInteractionMode = "chat" | "form" | "hybrid";

export function deriveInteractionMode(inputs: TypedFields): InteractionMode {
  const types = Object.values(inputs).map((spec) => compactFieldType(spec)).filter(Boolean);
  if (!types.length) return "chat";
  const artifacts = types.filter((item) => isArtifactCompactType(item) || item === "artifact");
  const strings = types.filter((item) => item === "string");
  if (artifacts.length && strings.length) return "hybrid";
  if (types.length === 1 && types[0] === "string") return "chat";
  if (types.length >= 2 || artifacts.length) return "form";
  return "auto";
}

export function resolveInteractionMode(source: Pick<AgentSource, "inputs" | "extensions">): ResolvedInteractionMode {
  const declared = source.extensions.veyra.interaction_mode ?? "auto";
  if (declared === "chat" || declared === "form" || declared === "hybrid") return declared;
  const derived = deriveInteractionMode(source.inputs);
  return derived === "auto" ? "chat" : derived;
}

export function chatFieldName(inputs: TypedFields): string | null {
  const entries = Object.entries(inputs);
  const named = entries.find(([name, spec]) => compactFieldType(spec) === "string" && name === "message");
  if (named) return named[0];
  if (entries.length === 1 && compactFieldType(entries[0][1]) === "string") return entries[0][0];
  const strings = entries.filter(([, spec]) => compactFieldType(spec) === "string");
  return strings.at(-1)?.[0] ?? null;
}

export function committedVersions<T extends { committed?: boolean; created_at: string; version_id: string }>(versions: T[]): T[] {
  return [...versions]
    .filter((item) => item.committed)
    .sort((left, right) => left.created_at.localeCompare(right.created_at) || left.version_id.localeCompare(right.version_id));
}

export function versionNumber<T extends { committed?: boolean; created_at: string; version_id: string }>(versions: T[], versionId: string | null | undefined): number | null {
  if (!versionId) return null;
  const index = committedVersions(versions).findIndex((item) => item.version_id === versionId);
  return index >= 0 ? index + 1 : null;
}
