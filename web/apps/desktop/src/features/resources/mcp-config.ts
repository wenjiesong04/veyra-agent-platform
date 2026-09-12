/** Parse standard MCP server configuration without importing secret values. */

export type ImportedMcpServer = {
  name: string;
  command?: string;
  args: string[];
  env_names: Record<string, string>;
  transport: "stdio" | "streamable_http";
  url: string | null;
  headers: Record<string, string>;
  enabled: boolean;
};

const MAX_SERVERS = 32;
const MAX_ARGS = 64;
const NAME = /^[A-Za-z][A-Za-z0-9._-]{0,63}$/;
const ENV_NAME = /^[A-Z][A-Z0-9_]{0,127}$/;
const SECRET_REF = /^[a-z][a-z0-9_-]{0,63}\.[a-z][a-z0-9_.-]{0,127}$/;
const ENV_TEMPLATE = /^\$\{([A-Z][A-Z0-9_]{0,127})\}$/;
const ENV_PLACEHOLDER = /\$\{([A-Z][A-Z0-9_]{0,127})\}/g;
const HEADER_NAME = /^[A-Za-z][A-Za-z0-9-]{0,127}$/;
const RESERVED_HEADERS = new Set(["accept", "content-type", "mcp-protocol-version", "mcp-session-id"]);
const SENSITIVE_HEADERS = ["authorization", "token", "key", "secret", "credential"];

export class McpConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "McpConfigError";
  }
}

export function parseMcpConfig(input: unknown): ImportedMcpServer[] {
  if (!isRecord(input)) throw new McpConfigError("MCP config must be a JSON object.");
  const raw = input.mcpServers ?? input.servers;
  const entries = Array.isArray(raw)
    ? raw.map((item, index) => [String(index), item] as const)
    : isRecord(raw)
      ? Object.entries(raw)
      : [];
  if (!entries.length) throw new McpConfigError("MCP config has no servers.");
  if (entries.length > MAX_SERVERS) throw new McpConfigError("MCP config contains too many servers.");

  const names = new Set<string>();
  return entries.map(([key, value]) => {
    if (!isRecord(value)) throw new McpConfigError("Each MCP server must be an object.");
    const name = typeof value.name === "string" ? value.name.trim() : key.trim();
    if (!NAME.test(name)) throw new McpConfigError("MCP server names must be safe identifiers.");
    if (names.has(name)) throw new McpConfigError("MCP server names must be unique.");
    names.add(name);
    const args = value.args === undefined ? [] : value.args;
    if (!Array.isArray(args) || args.length > MAX_ARGS || args.some((item) => typeof item !== "string" || !item || item.includes("\0"))) {
      throw new McpConfigError("MCP args must be a bounded string array.");
    }
    const hasUrl = typeof value.url === "string" && value.url.trim().length > 0;
    const hasCommand = typeof value.command === "string" && value.command.trim().length > 0;
    if (hasUrl === hasCommand) {
      throw new McpConfigError("Each MCP server needs exactly one command or URL.");
    }
    const transport = hasUrl ? "streamable_http" as const : "stdio" as const;
    if (transport === "streamable_http" && (args.length > 0 || hasEntries(value.env_names) || hasEntries(value.env))) {
      throw new McpConfigError("HTTP MCP servers cannot define subprocess args or environment bindings.");
    }
    const rawEnv = value.env_names ?? value.env ?? {};
    if (!isRecord(rawEnv)) throw new McpConfigError("MCP environment bindings must be an object.");
    const env_names: Record<string, string> = {};
    for (const [envName, binding] of Object.entries(rawEnv)) {
      if (!ENV_NAME.test(envName) || typeof binding !== "string") {
        throw new McpConfigError("MCP environment names must be uppercase identifiers.");
      }
      env_names[envName] = normalizeBinding(binding);
    }
    const rawHeaders = value.headers ?? value.header_templates ?? {};
    if (!isRecord(rawHeaders)) throw new McpConfigError("MCP HTTP headers must be an object.");
    const headers: Record<string, string> = {};
    for (const [headerName, headerValue] of Object.entries(rawHeaders)) {
      if (!HEADER_NAME.test(headerName) || RESERVED_HEADERS.has(headerName.toLowerCase()) || typeof headerValue !== "string") {
        throw new McpConfigError("MCP HTTP header bindings are invalid.");
      }
      headers[headerName] = normalizeHeaderValue(headerName, headerValue);
    }
    if (transport === "stdio" && Object.keys(headers).length > 0) {
      throw new McpConfigError("stdio MCP servers cannot define HTTP headers.");
    }
    return {
      name,
      ...(transport === "stdio" && typeof value.command === "string" ? { command: value.command.trim() } : {}),
      args: transport === "stdio" ? [...args] as string[] : [],
      env_names,
      transport,
      url: transport === "streamable_http" && typeof value.url === "string" ? value.url.trim() : null,
      headers,
      enabled: value.enabled === undefined ? value.disabled !== true : value.enabled === true,
    };
  });
}

function normalizeBinding(value: string): string {
  const binding = value.trim();
  const template = binding.match(ENV_TEMPLATE)?.[1];
  if (template) return template;
  if (ENV_NAME.test(binding) || SECRET_REF.test(binding)) return binding;
  throw new McpConfigError("MCP config may contain environment names or secret references only; plaintext credentials were not imported.");
}

function normalizeHeaderValue(name: string, value: string): string {
  const headerValue = value.trim();
  if (!headerValue || headerValue.length > 2_000 || headerValue.includes("\r") || headerValue.includes("\n")) {
    throw new McpConfigError("MCP HTTP header bindings are invalid.");
  }
  const placeholders = [...headerValue.matchAll(ENV_PLACEHOLDER)];
  if (headerValue.includes("${") && !placeholders.length) {
    throw new McpConfigError("MCP HTTP header references must use uppercase environment placeholders.");
  }
  const sensitive = SENSITIVE_HEADERS.some((part) => name.toLowerCase().includes(part));
  if (sensitive && !placeholders.length && !ENV_NAME.test(headerValue) && !SECRET_REF.test(headerValue)) {
    throw new McpConfigError("Sensitive MCP headers must use an environment or secret reference.");
  }
  return headerValue;
}

function hasEntries(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
