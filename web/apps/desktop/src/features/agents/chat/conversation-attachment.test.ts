import { describe, expect, it } from "vitest";
import { attachmentsToPrompt, composeFactoryPrompt, isConversationFile, readConversationFile } from "./conversation-attachment";

describe("conversation attachments", () => {
  it("accepts text and office documents only", () => {
    expect(isConversationFile("notes.txt")).toBe(true);
    expect(isConversationFile("brief.docx")).toBe(true);
    expect(isConversationFile("scan.pdf")).toBe(true);
    expect(isConversationFile("photo.png")).toBe(false);
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
});
