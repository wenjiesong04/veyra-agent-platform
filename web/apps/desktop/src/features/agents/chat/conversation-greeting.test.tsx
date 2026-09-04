import { describe, expect, it } from "vitest";
import { assembleGreeting } from "./conversation-greeting";

describe("assembleGreeting", () => {
  it("names the Project in the build prompt", () => {
    expect(assembleGreeting("en", "New Agent")).toBe("What do you want to achieve in New Agent?");
    expect(assembleGreeting("zh", "New Agent")).toBe("你想在 New Agent 实现什么？");
  });

  it("names the Agent when opening an existing one", () => {
    expect(assembleGreeting("en", "Alpha", "Reviewer")).toBe("What do you want to achieve in Reviewer?");
    expect(assembleGreeting("zh", "Alpha", "Reviewer")).toBe("你想在 Reviewer 实现什么？");
  });

  it("falls back to a new Project when nothing is selected", () => {
    expect(assembleGreeting("en")).toBe("What do you want to achieve in a new project?");
    expect(assembleGreeting("zh")).toBe("你想在 新项目 实现什么？");
  });
});
