import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FactoryStatus } from "@veyra/api-contracts";
import { ThemeProvider } from "@veyra/ui";
import { FactoryCapabilitySummary } from "./factory-capability-summary";

const status: FactoryStatus = {
  schema_version: "1.0",
  configured: true,
  model_id: "kimi-k3",
  model_base_url: "https://api.moonshot.cn/v1",
  model_api_key_env: "MOONSHOT_API_KEY",
  reasoning_effort: "high",
  repair_attempts: 3,
  executes_drafts: false,
  capability_profile: {
    schema_version: "1.0",
    provider_id: "moonshot",
    provider_family: "moonshot",
    model: "kimi-k3",
    endpoint_kind: "chat_completions",
    base_url_fingerprint: "fingerprint",
    structured_output: "json_schema",
    schema_flavor: "moonshot_mfjs",
    schema_profile: "mfjs",
    strict_json_schema: true,
    json_object_fallback: true,
    reasoning_effort: true,
    supports_reasoning_effort: true,
    strict_json_schema_support: "unknown",
    json_object_support: "unknown",
    source: "static_known",
    status: "inconclusive",
    checked_at: "2026-09-19T12:00:00Z",
    probe_version: "semantic-plan-ok-v1",
    probed: false,
    error_class: "rate_limited",
    summary: {
      provider: "Moonshot",
      model: "kimi-k3",
      structured_output: "Strict JSON Schema",
      schema_profile: "MFJS",
      json_object_fallback: "Supported",
      status: "Inconclusive",
      checked_at: "2026-09-19T12:00:00Z",
      error_class: "rate_limited",
    },
  },
};

afterEach(cleanup);

describe("FactoryCapabilitySummary", () => {
  it("shows a light protocol summary and does not say unsupported after 429", async () => {
    const onRecheck = vi.fn();
    render(
      <ThemeProvider>
        <FactoryCapabilitySummary status={status} locale="zh" busy={false} onRecheck={onRecheck} />
      </ThemeProvider>,
    );
    expect(screen.getByText("Moonshot")).toBeTruthy();
    expect(screen.getByText("kimi-k3")).toBeTruthy();
    expect(screen.getByText("Strict JSON Schema")).toBeTruthy();
    expect(screen.getByText("MFJS")).toBeTruthy();
    expect(screen.getByText("Inconclusive")).toBeTruthy();
    expect(screen.queryByText("Not supported")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "重新检测" }));
    expect(onRecheck).toHaveBeenCalledTimes(1);
  });
});
