import { describe, expect, it } from "vitest";
import { connectionFailureMessage } from "./connection-feedback";

describe("connection access refusal", () => {
  it.each(["zh", "en"] as const)("keeps the %s HTTP 403 explanation neutral for both error codes", (locale) => {
    const message = connectionFailureMessage("runtime_permission_denied", locale);
    expect(connectionFailureMessage("runtime_forbidden", locale)).toBe(message);
    expect(message).toContain("HTTP 403");
    expect(message).toContain(locale === "zh" ? "无法确定具体原因" : "does not establish the cause");
    for (const label of locale === "zh" ? ["模型", "地域", "工作空间", "密钥配置", "执行记录"] : ["model", "region", "workspace", "key configuration", "execution record"]) {
      expect(message).toContain(label);
    }
    expect(message).not.toMatch(/更换密钥|密钥没有.*权限|replace the key|key lacks permission/);
  });

  it("does not project HTTP 403 onto other connection failures", () => {
    expect(connectionFailureMessage("runtime_unauthorized", "en")).not.toContain("403");
    expect(connectionFailureMessage("runtime_insufficient_balance", "zh")).toContain("余额或可用额度不足");
    expect(connectionFailureMessage("unknown", "zh")).toBe("这次测试未完成，请检查连接设置后重试。");
  });
});
