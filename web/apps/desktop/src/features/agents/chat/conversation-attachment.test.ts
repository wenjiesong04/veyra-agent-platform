import { describe, expect, it } from "vitest";
import { attachmentsToPrompt, clipboardCaption, composeFactoryPrompt, ensureClipboardFileName, isConversationFile, readConversationFile } from "./conversation-attachment";

describe("conversation attachments", () => {
  it("accepts text and office documents only", () => {
    expect(isConversationFile("notes.txt")).toBe(true);
    expect(isConversationFile("brief.docx")).toBe(true);
    expect(isConversationFile("scan.pdf")).toBe(true);
    expect(isConversationFile("photo.png")).toBe(true);
    expect(isConversationFile("vector.svg", "image/svg+xml")).toBe(false);
  });

  it("reads text files into the Factory prompt", async () => {
    const file = new File(["Quarterly notes"], "notes.txt", { type: "text/plain" });
    const attachment = await readConversationFile(file, "att-1");
    expect(attachment).toMatchObject({ kind: "text", name: "notes.txt", text: "Quarterly notes" });
    expect(composeFactoryPrompt("Write a brief", [attachment], "en")).toContain("Quarterly notes");
  });

  it("keeps PDF and Word files as unread document examples", async () => {
    const file = new File([new Uint8Array([37, 80, 68, 70])], "report.pdf", { type: "application/pdf" });
    const attachment = await readConversationFile(file, "att-2");
    expect(attachment.kind).toBe("document");
    expect(attachment.text).toBeUndefined();
    expect(attachmentsToPrompt([attachment], "en")).toMatch(/did not extract its body/);
  });

  it("creates a local image preview without placing pixels or a data URL in the Builder prompt", async () => {
    const image = new File(["fake-pixels"], "front.png", { type: "image/png" });
    const attachment = await readConversationFile(image, "image-1");
    const prompt = composeFactoryPrompt("Review this image", [attachment], "en");
    expect(attachment).toMatchObject({ kind: "image", mediaType: "image/png", name: "front.png" });
    expect(attachment.previewUrl).toMatch(/^blob:/);
    expect(prompt).toContain("does not analyze image pixels");
    expect(prompt).not.toContain("fake-pixels");
    expect(prompt).not.toContain("data:image");
  });

  it("uses a fixed safe filename for unnamed clipboard images and omits local file paths", () => {
    const image = new File(["pixels"], "", { type: "image/png" });
    const named = ensureClipboardFileName(image, 2);
    expect(named.name).toMatch(/^pasted-file-\d+-2\.png$/);
    expect(clipboardCaption("file:///Users/alice/Desktop/front.png", [named])).toBe("");
    expect(clipboardCaption("/Users/alice/Desktop/front.png", [named])).toBe("");
    expect(clipboardCaption("Please review this", [named])).toBe("Please review this");
  });
});
