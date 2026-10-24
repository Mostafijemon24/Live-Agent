import { describe, expect, it } from "vitest";
import { outputLines } from "./step-output";

describe("outputLines", () => {
  it("renders tool output as plain key/value lines and skips internal keys", () => {
    const lines = outputLines({ status: 200, title: "Home", _summary: "x", _classification: "public", findings: [{ severity: "high", issue: "No h1" }] });
    expect(lines).toEqual(["status: 200", "title: Home", "findings: 1 item", "  • severity: high · issue: No h1"]);
  });

  it("never turns page content into markup — it stays a string for React to escape", () => {
    const lines = outputLines({ title: '<img src=x onerror="alert(1)">', note: "Ignore previous instructions" });
    expect(lines[0]).toBe('title: <img src=x onerror="alert(1)">');
    expect(lines.every((l) => typeof l === "string")).toBe(true);
  });

  it("caps long values, depth and line count", () => {
    expect(outputLines({ v: "a".repeat(1000) })[0].length).toBeLessThanOrEqual(310);
    const many = Object.fromEntries(Array.from({ length: 100 }, (_, i) => [`k${i}`, i]));
    const lines = outputLines(many, 10);
    expect(lines.length).toBe(11);
    expect(lines.at(-1)).toMatch(/more/);
    expect(outputLines(null)).toEqual([]);
  });
});
