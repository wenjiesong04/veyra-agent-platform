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
      transport: "stdio",
      url: null,
      headers: {},
      enabled: true,
    }]);
  });

  it("accepts Veyra-style server arrays and secret references", () => {
    expect(parseMcpConfig({
      servers: [{ name: "github", command: "node", env_names: { TOKEN: "github.main" }, disabled: true }],
    })[0]).toMatchObject({ name: "github", env_names: { TOKEN: "github.main" }, transport: "stdio", enabled: false });
  });

  it("imports a Streamable HTTP endpoint with a non-secret header template", () => {
    expect(parseMcpConfig({
      mcpServers: {
        remote: {
          url: "https://example.com/mcp",
          headers: { Authorization: "Bearer ${MCP_TOKEN}", "X-Client": "veyra" },
        },
      },
    })[0]).toEqual({
      name: "remote",
      args: [],
      env_names: {},
      transport: "streamable_http",
      url: "https://example.com/mcp",
      headers: { Authorization: "Bearer ${MCP_TOKEN}", "X-Client": "veyra" },
      enabled: true,
    });
  });

  it("rejects plaintext credentials instead of sending them to the sidecar", () => {
    expect(() => parseMcpConfig({ mcpServers: { private: { command: "node", env: { TOKEN: "sk-live-secret" } } } })).toThrow(McpConfigError);
  });
});
