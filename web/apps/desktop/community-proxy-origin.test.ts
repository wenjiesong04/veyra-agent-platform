import { describe, expect, it } from "vitest";
import { isLoopbackHttpOrigin, rewriteOriginForCommunityProxy } from "./community-proxy-origin";

describe("rewriteOriginForCommunityProxy", () => {
  it("rewrites Desktop and Community loopback origins to the Community service origin", () => {
    expect(rewriteOriginForCommunityProxy("http://127.0.0.1:5173", "http://127.0.0.1:8772")).toBe("http://127.0.0.1:8772");
    expect(rewriteOriginForCommunityProxy("http://localhost:5174", "http://127.0.0.1:8772")).toBe("http://127.0.0.1:8772");
    expect(isLoopbackHttpOrigin("http://127.0.0.1:5173")).toBe(true);
  });

  it("leaves cross-site origins unchanged so Community can reject them", () => {
    expect(rewriteOriginForCommunityProxy("https://attacker.example", "http://127.0.0.1:8772")).toBe("https://attacker.example");
    expect(isLoopbackHttpOrigin("https://attacker.example")).toBe(false);
  });
});
