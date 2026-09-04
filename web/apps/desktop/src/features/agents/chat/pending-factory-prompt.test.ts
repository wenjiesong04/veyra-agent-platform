import { afterEach, describe, expect, it } from "vitest";
import { takePendingFactoryPrompt, writePendingFactoryPrompt } from "./pending-factory-prompt";

describe("pending factory prompt", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("stores a prompt once and clears it on take", () => {
    writePendingFactoryPrompt("  Assemble a brief  ");
    expect(takePendingFactoryPrompt()).toBe("Assemble a brief");
    expect(takePendingFactoryPrompt()).toBeUndefined();
  });
});
