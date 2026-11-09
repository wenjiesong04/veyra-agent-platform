import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { errorCopy } from "@veyra/connected-account";
import { CommunityApp } from "./app";

const account = {
  id: "01a-user",
  email: "alice@example.com",
  handle: "veyra-alice",
  display_name: "Alice",
  avatar_url: null,
};

const currentSession = {
  id: "session-current",
  device_name: "Alice Mac",
  user_agent: "Test browser",
  created_at: "2026-08-25T08:00:00Z",
  last_seen_at: "2026-08-26T08:00:00Z",
  expires_at: "2026-09-25T08:00:00Z",
  current: true,
};

function jsonResponse(status: number, body: object): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
}

function requestMethod(init?: RequestInit): string {
  return (init?.method ?? "GET").toUpperCase();
}

function requestBody(init?: RequestInit): Record<string, unknown> {
  return typeof init?.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : {};
}

beforeEach(() => {
  window.localStorage.clear();
  document.cookie = "veyra-csrf=; Max-Age=0; path=/";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("Community account flows", () => {
  it("routes to login and signs in with email and password", async () => {
    window.location.hash = "#/login";
    const requests: Array<{ url: string; method: string; body: Record<string, unknown>; csrf: string | null }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const method = requestMethod(init);
      const body = requestBody(init);
      requests.push({ url, method, body, csrf: new Headers(init?.headers).get("X-CSRF-Token") });
      if (url.endsWith("/account/me")) return jsonResponse(401, { detail: "authentication_required" });
      if (url.endsWith("/auth/login")) return jsonResponse(200, { schema_version: "community.auth.v1", authenticated: true, account });
      if (url.endsWith("/account/sessions")) return jsonResponse(200, { schema_version: "community.account.v1", sessions: [currentSession] });
      return jsonResponse(404, { detail: "not_found" });
    }));

    const user = userEvent.setup();
    render(<CommunityApp />);
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    expect(screen.getByLabelText("Password")).toHaveAttribute("minlength", "8");
    expect(screen.getByLabelText("Password")).not.toHaveAttribute("maxlength");
    await user.type(screen.getByLabelText("Password"), "maplexyz");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(window.location.hash).toBe("#/account"));
    expect(requests.find((request) => request.url.endsWith("/auth/login"))?.body).toMatchObject({ email: "alice@example.com", password: "maplexyz" });
    expect(window.localStorage.getItem("account")).toBeNull();
  });

  it("explains credential failures without enumerating whether the email exists", async () => {
    window.location.hash = "#/login";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/account/me")) return jsonResponse(401, { detail: "authentication_required" });
      if (url.endsWith("/auth/login")) return jsonResponse(401, { detail: "invalid_credentials" });
      return jsonResponse(404, { detail: "not_found" });
    }));

    const user = userEvent.setup();
    render(<CommunityApp />);
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "wrongpass");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(errorCopy.en.invalidCredentials);
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByText(errorCopy.en.generic)).not.toBeInTheDocument();
    expect(screen.queryByText(/not registered|does not exist/i)).not.toBeInTheDocument();
  });

  it("explains Community downtime instead of a generic retry banner", async () => {
    window.location.hash = "#/login";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/account/me")) return jsonResponse(401, { detail: "authentication_required" });
      if (url.endsWith("/auth/login")) return jsonResponse(503, { detail: "community_unavailable" });
      return jsonResponse(404, { detail: "not_found" });
    }));

    const user = userEvent.setup();
    render(<CommunityApp />);
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "maplexyz");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(errorCopy.en.network);
  });

  it("explains a rejected browser origin", async () => {
    window.location.hash = "#/login";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/account/me")) return jsonResponse(401, { detail: "authentication_required" });
      if (url.endsWith("/auth/login")) return jsonResponse(403, { detail: "origin_not_allowed" });
      return jsonResponse(404, { detail: "not_found" });
    }));

    const user = userEvent.setup();
    render(<CommunityApp />);
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    await user.type(screen.getByLabelText("Password"), "maplexyz");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(errorCopy.en.origin);
  });

  it("registers through email, six-digit code, and profile steps", async () => {
    window.location.hash = "#/register";
    const requests: Array<{ url: string; body: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const body = requestBody(init);
      requests.push({ url, body });
      if (url.endsWith("/account/me")) return jsonResponse(401, { detail: "authentication_required" });
      if (url.endsWith("/auth/verification-codes")) return jsonResponse(202, { schema_version: "community.auth.v1", accepted: true });
      if (url.endsWith("/auth/register")) return jsonResponse(201, { schema_version: "community.auth.v1", authenticated: true, account });
      if (url.endsWith("/account/sessions")) return jsonResponse(200, { schema_version: "community.account.v1", sessions: [currentSession] });
      return jsonResponse(404, { detail: "not_found" });
    }));

    const user = userEvent.setup();
    render(<CommunityApp />);
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    await user.click(screen.getByRole("button", { name: "Send verification code" }));
    expect(await screen.findByRole("heading", { name: "Enter the six-digit code" })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Verification code/), "482913");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText(/Name/), "Alice");
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute("minlength", "8");
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute("maxlength", "64");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("minlength", "8");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("maxlength", "64");
    expect(screen.getByText("8–64 characters")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Password/), "maplexyz");
    await user.type(screen.getByLabelText("Confirm password"), "maplexyz");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(window.location.hash).toBe("#/account"));

    expect(requests.find((request) => request.url.endsWith("/auth/verification-codes"))?.body).toMatchObject({ email: "alice@example.com", purpose: "registration" });
    const registration = requests.find((request) => request.url.endsWith("/auth/register"))?.body;
    expect(registration).toMatchObject({ email: "alice@example.com", verification_code: "482913", display_name: "Alice" });
    expect(registration).not.toHaveProperty("handle");
  });

  it("confirms a new password and clears an authenticated account", async () => {
    window.location.hash = "#/forgot-password";
    const requests: Array<{ url: string; body: Record<string, unknown> }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const body = requestBody(init);
      requests.push({ url, body });
      if (url.endsWith("/account/me")) return jsonResponse(200, { schema_version: "community.account.v1", account });
      if (url.endsWith("/auth/verification-codes")) return jsonResponse(202, { schema_version: "community.auth.v1", accepted: true });
      if (url.endsWith("/auth/password-reset/confirm")) return jsonResponse(200, { schema_version: "community.auth.v1", reset: true });
      return jsonResponse(404, { detail: "not_found" });
    }));

    const user = userEvent.setup();
    render(<CommunityApp />);
    await user.type(screen.getByLabelText("Email"), "alice@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset code" }));
    await user.type(await screen.findByLabelText(/Verification code/), "239104");
    expect(screen.getByLabelText(/^New password/)).toHaveAttribute("minlength", "8");
    expect(screen.getByLabelText(/^New password/)).toHaveAttribute("maxlength", "64");
    expect(screen.getByLabelText("Confirm new password")).toHaveAttribute("minlength", "8");
    expect(screen.getByLabelText("Confirm new password")).toHaveAttribute("maxlength", "64");
    expect(screen.getByText("8–64 characters")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^New password/), "maplexyz");
    await user.type(screen.getByLabelText("Confirm new password"), "maplexyz");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Sign in with the new password" }));
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "You are already signed in" })).not.toBeInTheDocument();
    expect(requests.find((request) => request.url.endsWith("/auth/verification-codes"))?.body).toMatchObject({ purpose: "password_reset" });
    expect(requests.find((request) => request.url.endsWith("/auth/password-reset/confirm"))?.body).toMatchObject({ verification_code: "239104", new_password: "maplexyz" });
  });

  it("loads the account, updates the display name, and revokes a device session", async () => {
    window.location.hash = "#/community/mine/settings";
    const otherSession = { ...currentSession, id: "session-other", device_name: "Old browser", current: false };
    let currentAccount = account;
    let visibleSessions = [currentSession, otherSession];
    const requests: Array<{ url: string; method: string; body: Record<string, unknown>; csrf: string | null }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const method = requestMethod(init);
      const body = requestBody(init);
      requests.push({ url, method, body, csrf: new Headers(init?.headers).get("X-CSRF-Token") });
      if (url.endsWith("/account/me")) return jsonResponse(200, { schema_version: "community.account.v1", account: currentAccount });
      if (url.endsWith("/account/sessions") && method === "GET") return jsonResponse(200, { schema_version: "community.account.v1", sessions: visibleSessions });
      if (url.endsWith("/account/profile")) {
        currentAccount = { ...currentAccount, display_name: "Alice Chen" };
        return jsonResponse(200, { schema_version: "community.account.v1", account: currentAccount });
      }
      if (url.endsWith("/account/sessions/session-other") && method === "DELETE") {
        visibleSessions = visibleSessions.filter((session) => session.id !== "session-other");
        return new Response(null, { status: 204 });
      }
      return jsonResponse(404, { detail: "not_found" });
    }));

    document.cookie = "veyra-csrf=test-csrf; path=/";
    const user = userEvent.setup();
    render(<CommunityApp />);
    const name = await screen.findByLabelText("Display name");
    fireEvent.change(name, { target: { value: "Alice Chen" } });
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(requests.some((request) => request.url.endsWith("/account/profile"))).toBe(true), { timeout: 3000 });
    await waitFor(() => expect(screen.getByText("Profile updated.").closest('[role="status"]')).not.toBeNull(), { timeout: 3000 });
    await user.click(screen.getByRole("button", { name: "Revoke access" }));
    await waitFor(() => expect(screen.queryByText("Old browser")).not.toBeInTheDocument());

    expect(requests.find((request) => request.url.endsWith("/account/profile"))?.body).toEqual({ display_name: "Alice Chen" });
    expect(requests.some((request) => request.url.endsWith("/account/sessions/session-other") && request.method === "DELETE")).toBe(true);
    const profileRequest = requests.find((request) => request.url.endsWith("/account/profile"));
    expect(profileRequest?.csrf).toBe("test-csrf");
  });
});
