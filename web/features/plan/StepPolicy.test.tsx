import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { TaskStep } from "@/lib/api/types";
import { StepArgs, StepPolicy, StepResult } from "./StepPolicy";

const base: TaskStep = {
  id: "s",
  position: 1,
  title: "Inspect page",
  description: "",
  tool: "Inspect a web page",
  risk: "read_only",
  requires_approval: false,
  state: "done",
  selected: true,
  started_at: null,
  finished_at: null,
};

describe("StepResult / StepPolicy", () => {
  it("shows tool output as escaped text, never as HTML", () => {
    const { container } = render(
      <StepResult step={{ ...base, output_summary: "Inspected", output: { title: '<img src=x onerror="alert(1)"><b>bold</b>' } }} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });

  it("shows the server's policy decision, impact and destinations", () => {
    render(
      <StepPolicy
        step={{
          ...base,
          impact: "external_read",
          destinations: ["example.com"],
          classifications: ["public"],
          policy: { outcome: "deny", reasons: ["example.com is not on this workspace's allowed domains list."], data_leaves: false, classification: "public", version: "p3" },
        }}
      />,
    );
    expect(screen.getByText("Blocked by policy")).toBeTruthy();
    expect(screen.getByText("Reads an outside website")).toBeTruthy();
    expect(screen.getByText("example.com")).toBeTruthy();
    expect(screen.getByText(/allowed domains list/)).toBeTruthy();
  });

  it("shows the complete arguments as text (P3-SR-2)", () => {
    const code = "print(1)\n".repeat(80) + '<script>alert(1)</script>';
    const { container } = render(<StepArgs step={{ ...base, tool_id: "code.run_python", args: { code }, args_hash: "a".repeat(64) }} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("pre")?.textContent).toBe(code);
  });
});
