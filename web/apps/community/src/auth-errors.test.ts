import { describe, expect, it } from "vitest";
import { CommunityApiError, errorCopy, explainAuthError } from "@veyra/connected-account";

const copy = errorCopy.en;

function apiError(code: string, status = 400, validationMessages: string[] = []): CommunityApiError {
  return new CommunityApiError(code, { status, code, validationMessages });
}

describe("explainAuthError", () => {
  it("maps invalid credentials onto the password field and keeps unknown accounts generic", () => {
    const missing = explainAuthError(apiError("invalid_credentials", 401), copy, "login");
    const wrong = explainAuthError(apiError("invalid_credentials", 401), copy, "login");
    expect(missing).toEqual(wrong);
    expect(missing).toEqual({ message: copy.invalidCredentials, field: "password" });
    expect(missing.message).not.toMatch(/not registered|does not exist|unknown account/i);
  });

  it("maps Community downtime, proxy failures, and fetch errors to the network copy", () => {
    expect(explainAuthError(apiError("community_unavailable", 503), copy, "login").message).toBe(copy.network);
    expect(explainAuthError(apiError("network_unavailable", 0), copy, "login").message).toBe(copy.network);
    expect(explainAuthError(apiError("http_502", 502), copy, "login").message).toBe(copy.network);
    expect(explainAuthError(new TypeError("Failed to fetch"), copy, "login").message).toBe(copy.network);
  });

  it("maps origin, CSRF, rate limits, and server failures to actionable copy", () => {
    expect(explainAuthError(apiError("origin_not_allowed", 403), copy, "login").message).toBe(copy.origin);
    expect(explainAuthError(apiError("csrf_failed", 403), copy, "login").message).toBe(copy.csrf);
    expect(explainAuthError(apiError("http_429", 429), copy, "login").message).toBe(copy.rateLimited);
    expect(explainAuthError(apiError("http_500", 500), copy, "login").message).toBe(copy.server);
    expect(explainAuthError(apiError("http_418", 418), copy, "login").message).toBe(copy.genericWithStatus.replace("{status}", "418"));
  });

  it("does not treat an expired account session as a bad password", () => {
    expect(explainAuthError(apiError("authentication_required", 401), copy, "account")).toEqual({
      message: copy.sessionExpired,
    });
  });
});
