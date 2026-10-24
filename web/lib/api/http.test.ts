import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpAgentApi } from "./http";
import { ApiError } from "./client";

afterEach(() => vi.unstubAllGlobals());

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

describe("HttpAgentApi", () => {
  it("surfaces server errors with code, message and request id — never a fake success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respond(404, { error: { code: "not_found", message: "That task was not found in your workspace.", request_id: "req-123456789", details: null } })));
    const api = new HttpAgentApi();
    await expect(api.getTask("x")).rejects.toMatchObject({ status: 404, code: "not_found", requestId: "req-123456789" });
  });

  it("maps network failures to a clear error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await new HttpAgentApi().dashboard().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network_error");
  });

  it("sends the CSRF token on writes and the idempotency key on task creation", async () => {
    document.cookie = "stw_csrf=tok-abc";
    const fetchMock = vi.fn(async () => respond(201, { id: "t1" }));
    vi.stubGlobal("fetch", fetchMock);
    await new HttpAgentApi().createTask({ prompt: "Do a careful thing", type: "research", priority: "normal", mode: "plan_only" }, "idem-1");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("tok-abc");
    expect(headers["Idempotency-Key"]).toBe("idem-1");
    expect(init.credentials).toBe("same-origin");
  });

  it("exposes field errors from validation responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respond(422, { error: { code: "validation_error", message: "Some fields need attention.", request_id: "r", details: [{ field: "email", message: "Enter a valid email." }] } })));
    const err = (await new HttpAgentApi().forgotPassword("x").catch((e) => e)) as ApiError;
    expect(err.fieldErrors()).toEqual({ email: "Enter a valid email." });
  });
});
