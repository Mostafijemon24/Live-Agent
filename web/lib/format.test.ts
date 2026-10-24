import { describe, expect, it } from "vitest";
import { emailOk, fmtBytes, guessType, passwordOk, suggestTitle } from "./format";

describe("format helpers (ported from the prototype)", () => {
  it("validates email and password like the server", () => {
    expect(emailOk("name@example.com")).toBe(true);
    expect(emailOk("nope")).toBe(false);
    expect(passwordOk("short1")).toBe(false);
    expect(passwordOk("longenough1")).toBe(true);
    expect(passwordOk("no-digits-here")).toBe(false);
  });
  it("guesses task types and titles", () => {
    expect(guessType("Audit my WordPress site")).toBe("website");
    expect(guessType("Summarise the attached CSV")).toBe("file_analysis");
    expect(suggestTitle("audit my wordpress website for seo problems and more words")).toBe("Audit my wordpress website for seo problems…");
  });
  it("formats sizes", () => {
    expect(fmtBytes(512)).toBe("512 B");
    expect(fmtBytes(2048)).toBe("2 KB");
    expect(fmtBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});
