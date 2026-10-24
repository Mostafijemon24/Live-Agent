import { describe, expect, it } from "vitest";
import { sameOriginPath } from "./safe-path";

describe("sameOriginPath (SR-2 open redirect)", () => {
  it.each([
    "//evil.example",
    "/\\evil.example",
    "/\t/evil.example/phish",
    "/\n/evil.example",
    "/\r/evil.example",
    "/%09/evil.example",
    "/%0a/evil.example",
    "/%5c/evil.example",
    "https://evil.example",
    "javascript:alert(1)",
    " /tasks",
    "",
    null,
  ])("rejects %j", (v) => {
    expect(sameOriginPath(v as string | null)).toBeNull();
  });

  it.each([
    ["/tasks", "/tasks"],
    ["/tasks?status=running", "/tasks?status=running"],
    ["/approvals?id=abc#top", "/approvals?id=abc#top"],
    ["/tasks/123/plan", "/tasks/123/plan"],
  ])("keeps %j", (v, want) => {
    expect(sameOriginPath(v)).toBe(want);
  });
});
