import { describe, expect, it } from "vitest";
import { LOBSTER_PALETTE } from "./palette.js";

describe("LOBSTER_PALETTE", () => {
  it("defines all expected semantic color tokens", () => {
    expect(Object.keys(LOBSTER_PALETTE)).toEqual([
      "accent",
      "accentBright",
      "accentDim",
      "info",
      "success",
      "warn",
      "error",
      "muted",
    ]);
  });

  it("uses valid 6-digit hexadecimal color values", () => {
    const hexColor = /^#[0-9A-F]{6}$/;

    for (const color of Object.values(LOBSTER_PALETTE)) {
      expect(color).toMatch(hexColor);
    }
  });
});
