/** Parse standard MCP server configuration without importing secret values. */

export type ImportedMcpServer = {
  name: string;
  command: string;
  args: string[];
  env_names: Record<string, string>;
  enabled: boolean;
};

const MAX_SERVERS = 32;
const MAX_ARGS = 64;
const NAME = /^[A-Za-z][A-Za-z0-9._-]{0,63}$/;
const ENV_NAME = /^[A-Z][A-Z0-9_]{0,127}$/;
const SECRET_REF = /^[a-z][a-z0-9_-]{0,63}\.[a-z][a-z0-9_.-]{0,127}$/;
const ENV_TEMPLATE = /^\$\{([A-Z][A-Z0-9_]{0,127})\}$/;

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
    if (typeof value.command !== "string" || !value.command.trim()) {
      throw new McpConfigError("Each MCP server needs a command.");
    }
    const args = value.args === undefined ? [] : value.args;
    if (!Array.isArray(args) || args.length > MAX_ARGS || args.some((item) => typeof item !== "string" || !item || item.includes("\0"))) {
      throw new McpConfigError("MCP args must be a bounded string array.");
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
    return {
      name,
      command: value.command.trim(),
      args: [...args] as string[],
      env_names,
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
