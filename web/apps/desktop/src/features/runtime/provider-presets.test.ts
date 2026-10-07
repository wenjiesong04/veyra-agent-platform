import { describe, expect, it } from "vitest";
import { PROVIDER_PRESETS, normalizeServiceAddress, presetForAddress, serviceAddressIssue } from "./provider-presets";

describe("provider service addresses", () => {
  it("keeps the API endpoint separate from account webpages for every preset", () => {
    for (const preset of PROVIDER_PRESETS.filter((item) => item.address)) {
      expect(serviceAddressIssue(preset.address, "en")).toBe("");
      expect(new URL(preset.address).protocol).toBe("https:");
    }
    expect(presetForAddress("https://bailian.console.aliyun.com/cn-beijing/settings/api-key")?.id).toBe("dashscope");
    expect(serviceAddressIssue("https://bailian.console.aliyun.com/cn-beijing/settings/api-key", "zh")).toContain("网页");
  });

  it("accepts an independent compatible service and normalizes a pasted operation endpoint", () => {
    const address = "https://independent.example/api/v7/images/generations/";
    expect(serviceAddressIssue(address, "en")).toBe("");
    expect(presetForAddress(address)).toBeUndefined();
    expect(normalizeServiceAddress(address)).toBe("https://independent.example/api/v7");
  });

  it.each([
    "https://api.openai.com.evil.example/v1",
    "https://api.deepseek.com.evil.example/v1",
    "https://moonshot-relay.example/v1",
    "https://my-siliconflow-relay.example/v1",
  ])("does not identify an unrelated hostname as an official preset: %s", (address) => {
    expect(presetForAddress(address)).toBeUndefined();
  });

  it("recognizes a workspace-specific service region without discarding a dedicated address", () => {
    expect(presetForAddress("https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")?.id).toBe("dashscope_intl");
    expect(presetForAddress("https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")?.id).toBe("dashscope");
    expect(normalizeServiceAddress("https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")).toBe("https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1");
  });

  it.each([
    "https://user:fake-key@example.com/v1",
    "https://example.com/v1?api_key=fake-key",
    "https://example.com/v1#fake-key",
    "file:///tmp/api",
  ])("rejects credentials in the address and non-HTTP protocols: %s", (address) => {
    const issue = serviceAddressIssue(address, "en");
    expect(issue).not.toBe("");
    expect(issue).not.toContain("fake-key");
  });
});
