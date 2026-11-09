import { describe, expect, it } from "vitest";
import { LocalApiClientError } from "../../api/local-client";
import { productError, productRunError } from "./app-errors";

describe("model timeout errors", () => {
  it.each(["zh", "en"] as const)("uses the same actionable %s message for request and persisted Run errors", (locale) => {
    const error = new LocalApiClientError("Raw provider timeout", { status: 502, code: "runtime_timeout" });
    const mapped = productError(error, locale);
    expect(mapped.code).toBe("runtime_timeout");
    expect(productRunError(error.code, error.message, locale)).toBe(mapped.message);
    expect(mapped.message).toContain(locale === "zh" ? "失败阶段与超时设置" : "failed phase and timeout settings");
    expect(mapped.message).toContain(locale === "zh" ? "请勿直接重复" : "do not blindly repeat");
    expect(mapped.message).not.toContain("Raw provider");
  });

  it("does not guess a timeout or exhausted budget for unknown errors", () => {
    expect(productRunError("unrecognized", "Original diagnosis", "zh")).toBe("Original diagnosis");
    expect(productError(new Error("Original diagnosis"), "en")).toEqual({ message: "Original diagnosis", code: undefined });
  });
});

describe("model service access refusal", () => {
  it.each(["zh", "en"] as const)("uses the same neutral %s explanation without changing the persisted error code", (locale) => {
    const error = new LocalApiClientError("This key does not have permission", { status: 403, code: "runtime_permission_denied" });
    const mapped = productError(error, locale);
    expect(mapped.code).toBe("runtime_permission_denied");
    expect(productRunError(error.code, error.message, locale)).toBe(mapped.message);
    expect(mapped.message).toContain("HTTP 403");
    expect(mapped.message).toContain(locale === "zh" ? "无法确定具体原因" : "does not establish the cause");
    for (const label of locale === "zh" ? ["模型", "地域", "工作空间", "密钥配置", "执行记录"] : ["model", "region", "workspace", "key configuration", "execution record"]) {
      expect(mapped.message).toContain(label);
    }
    expect(mapped.message).not.toMatch(/更换密钥|密钥没有.*权限|This key does not have permission|replace the key/);
  });
});
