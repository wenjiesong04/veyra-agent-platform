import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PluginPack } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import type { LocalProjectApi } from "../../api/local-client";
import { PluginPackPanel } from "./plugin-pack-panel";

function pack(state: PluginPack["state"] = "quarantined"): PluginPack {
  return {
    schema_version: "1.0",
    plugin_id: "veyra.plugin.research",
    name: "Research Pack",
    description: "A reviewable Skill and MCP bundle.",
    version: "1.0.0",
    license: null,
    content_hash: "a".repeat(64),
    state,
    skills: [{ path: "skills/research/SKILL.md", reference: "veyra.skill.research@1.0.0", name: "Research", description: "Research safely", instruction: "Use cited evidence." }],
    mcp_servers: [{ name: "docs", command: "node", args: ["server.js"], env_names: { TOKEN: "DOCS_TOKEN" }, transport: "stdio", url: null, headers: {}, enabled: false }],
    skill_resources: state === "active" ? ["veyra.workshop.skill.research-12345678@0.0.1"] : [],
    mcp_server_ids: state === "active" ? ["server-1"] : [],
    activation_error: null,
  };
}

afterEach(cleanup);

describe("PluginPackPanel", () => {
  it("reviews a quarantined pack before activating it", async () => {
    const user = userEvent.setup();
    let current = pack();
    const api = {
      listPluginPacks: vi.fn(async () => ({ schema_version: "1.0" as const, plugins: [current] })),
      importPluginPack: vi.fn(),
      addProjectResource: vi.fn().mockResolvedValue({}),
      activatePluginPack: vi.fn(async () => {
        current = pack("active");
        return { schema_version: "1.0" as const, plugin: current };
      }),
    } as unknown as LocalProjectApi;

    render(<ThemeProvider><PluginPackPanel api={api} projects={[{ project_id: "project-1", name: "Research" }]} zh /></ThemeProvider>);

    expect(await screen.findByText("Research Pack")).toBeInTheDocument();
    await user.click(screen.getByText("查看包内容"));
    expect(screen.getByText("Use cited evidence.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "审核并激活" }));
    await waitFor(() => expect(api.activatePluginPack).toHaveBeenCalledWith("veyra.plugin.research", "1.0.0", true));
    expect(await screen.findByText("已激活")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "绑定 Skill 到 Project" }));
    await waitFor(() => expect(api.addProjectResource).toHaveBeenCalledWith("project-1", { reference: "veyra.workshop.skill.research-12345678@0.0.1", source: "imported" }));
    expect(await screen.findByText(/已将 1 个 Skill 绑定到 Research/)).toBeInTheDocument();
  });
});
