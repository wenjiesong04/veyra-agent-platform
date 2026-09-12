import { describe, expect, it } from "vitest";
import { McpConfigError, parseMcpConfig } from "./mcp-config";

describe("parseMcpConfig", () => {
  it("normalizes a standard mcpServers object without importing secret values", () => {
    expect(parseMcpConfig({
      mcpServers: {
        docs: {
          command: "npx",
          args: ["-y", "@example/docs"],
          env: { API_KEY: "${DOCS_API_KEY}" },
        },
      },
    })).toEqual([{
      name: "docs",
      command: "npx",
      args: ["-y", "@example/docs"],
      env_names: { API_KEY: "DOCS_API_KEY" },
      enabled: true,
    }]);
  });

  it("accepts Veyra-style server arrays and secret references", () => {
    expect(parseMcpConfig({
      servers: [{ name: "github", command: "node", env_names: { TOKEN: "github.main" }, disabled: true }],
    })[0]).toMatchObject({ name: "github", env_names: { TOKEN: "github.main" }, enabled: false });
  });

  it("rejects plaintext credentials instead of sending them to the sidecar", () => {
    expect(() => parseMcpConfig({ mcpServers: { private: { command: "node", env: { TOKEN: "sk-live-secret" } } } })).toThrow(McpConfigError);
  });
});
