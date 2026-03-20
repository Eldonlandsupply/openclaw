import { describe, expect, it } from "vitest";
import { applyMasterPromptShortcut } from "./master-prompt.js";

describe("applyMasterPromptShortcut", () => {
  it("returns prompt unchanged when trigger is missing", () => {
    const input = "Please summarize the latest CI failures.";
    expect(applyMasterPromptShortcut(input)).toBe(input);
  });

  it("replaces the trigger phrase with the OpenClaw master prompt", () => {
    const output = applyMasterPromptShortcut("use the master prompt");
    expect(output).toContain("Repo: [Eldonlandsupply/sitescout-energy]");
    expect(output).toContain("Now begin PHASE 0.");
  });

  it("supports trigger phrase in mixed case inside larger text", () => {
    const output = applyMasterPromptShortcut("Please USE the MASTER prompt for this PR.");
    expect(output).toContain("FINAL REPORT");
    expect(output).toContain(
      "[AUDIT] find flaws, list failures, propose fixes, then give exact steps",
    );
  });
});
