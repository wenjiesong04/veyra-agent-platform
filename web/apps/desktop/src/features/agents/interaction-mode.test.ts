import { describe, expect, it } from "vitest";
import type { AgentSource } from "@veyra/api-contracts";
import { deriveInteractionMode, resolveInteractionMode, chatFieldName, committedVersions, versionNumber } from "./interaction-mode";

const source = (inputs: AgentSource["inputs"], mode?: AgentSource["extensions"]["veyra"]["interaction_mode"]): Pick<AgentSource, "inputs" | "extensions"> => ({
  inputs,
  extensions: { veyra: { runtime_profile: "guarded", secret_refs: [], permissions: { network_hosts: [], tools: [] }, verification: { required: false, checks: [] }, ...(mode ? { interaction_mode: mode } : {}) } },
});

describe("interaction mode", () => {
  it("derives chat, form, and hybrid from typed inputs", () => {
    expect(deriveInteractionMode({ message: "string" })).toBe("chat");
    expect(deriveInteractionMode({ topic: "string", audience: "string" })).toBe("form");
    expect(deriveInteractionMode({ item_image: "image", brand: "string" })).toBe("hybrid");
  });

  it("treats a missing mode as auto", () => {
    expect(resolveInteractionMode(source({ request: "string" }))).toBe("chat");
    expect(resolveInteractionMode(source({ topic: "string", n: "number" }))).toBe("form");
  });

  it("honors an explicit Agent-level mode", () => {
    expect(resolveInteractionMode(source({ topic: "string", n: "number" }, "chat"))).toBe("chat");
  });

  it("picks the conversational field and numbers committed versions", () => {
    expect(chatFieldName({ message: "string", brand: "string" })).toBe("message");
    const versions = [
      { version_id: "v1", committed: true, created_at: "2026-01-01T00:00:00Z" },
      { version_id: "v2", committed: false, created_at: "2026-01-02T00:00:00Z" },
      { version_id: "v3", committed: true, created_at: "2026-01-03T00:00:00Z" },
    ];
    expect(committedVersions(versions).map((item) => item.version_id)).toEqual(["v1", "v3"]);
    expect(versionNumber(versions, "v3")).toBe(2);
  });
});
