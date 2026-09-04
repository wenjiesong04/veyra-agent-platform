import { describe, expect, it } from "vitest";
import { chatTargetHref, folderLabel, sameChatTarget } from "./chat-scope";

describe("chat scope", () => {
  it("routes Project selection to that Project's new chat", () => {
    expect(chatTargetHref({ kind: "project", projectId: "p-one", name: "Alpha" })).toBe("#/projects/p-one/chat");
    expect(chatTargetHref({ kind: "agent", projectId: "p-one", agentId: "agent-1", name: "Reviewer", projectName: "Alpha" })).toBe("#/projects/p-one/agents/agent-1");
    expect(chatTargetHref({ kind: "new" })).toBe("#/chat");
  });

  it("reads the folder name from a Project path", () => {
    expect(folderLabel("/Users/test/Projects/veyra-agent-platform")).toBe("veyra-agent-platform");
  });

  it("compares selected targets", () => {
    expect(sameChatTarget({ kind: "new" }, { kind: "new" })).toBe(true);
    expect(sameChatTarget({ kind: "project", projectId: "a", name: "A" }, { kind: "project", projectId: "a", name: "A" })).toBe(true);
    expect(sameChatTarget({ kind: "project", projectId: "a", name: "A" }, { kind: "project", projectId: "b", name: "B" })).toBe(false);
  });
});
