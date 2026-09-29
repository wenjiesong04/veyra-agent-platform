import { describe, expect, it } from "vitest";
import { displayConversationTitle, looksLikeIdentity } from "./conversation-title";

describe("displayConversationTitle", () => {
  it("never falls back to a raw UUID", () => {
    const leaked = "01a0ca54-c517-787b-bd8d-d4034403f38c";
    expect(looksLikeIdentity(leaked)).toBe(true);
    expect(displayConversationTitle(leaked, "en")).toBe("New conversation");
    expect(displayConversationTitle(leaked, "zh")).toBe("新对话");
    expect(displayConversationTitle(null, "en")).toBe("New conversation");
    expect(displayConversationTitle("", "en", leaked)).toBe("New conversation");
    expect(displayConversationTitle(leaked, "en", "Summarize this packaging photo")).toBe(
      "Summarize this packaging photo",
    );
  });

  it("keeps a human title", () => {
    expect(displayConversationTitle("Packaging review", "en")).toBe("Packaging review");
  });

  it("summarizes structured run titles without exposing ArtifactRefs", () => {
    const artifactId = "artifact-secret-id";
    expect(displayConversationTitle(JSON.stringify({ message: "Review these photos", photo: { kind: "artifact", artifact_id: artifactId, media_type: "image/png", filename: "front.png" } }), "en"))
      .toBe("Review these photos");
    const formTitle = displayConversationTitle(JSON.stringify({ brand: "Acme", photos: [{ kind: "artifact", artifact_id: artifactId, media_type: "image/png", filename: "front.png" }] }), "en");
    expect(formTitle).toBe("Multi-field run · image attachment");
    expect(formTitle).not.toContain(artifactId);
  });

  it("fails closed when a backend-truncated structured title is not valid JSON", () => {
    const truncated = '{"brandname":"Acme","productimage":{"artifact_id":"art_private_01';
    const title = displayConversationTitle(truncated, "zh");
    expect(title).toBe("多字段运行 · 文件附件");
    expect(title).not.toContain("art_private_01");
  });
});
