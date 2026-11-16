import { describe, it, expect } from "vitest";
import { renderIcon } from "./icons";

describe("renderIcon", () => {
  it("renders a valid svg string for FileText", () => {
    const svg = renderIcon("FileText", { size: 16 });
    expect(svg).toContain('<svg xmlns="http://www.w3.org/2000/svg"');
    expect(svg).toContain('width="16"');
    expect(svg).toContain('height="16"');
    expect(svg).toContain('aria-hidden="true"');
    expect(svg).toContain("<path");
  });

  it("applies custom class name and strokeWidth", () => {
    const svg = renderIcon("Download", { size: 12, strokeWidth: 1.5, className: "custom-icon" });
    expect(svg).toContain('class="custom-icon"');
    expect(svg).toContain('stroke-width="1.5"');
  });

  it("returns empty string for invalid icon name", () => {
    // @ts-expect-error testing invalid icon name
    const svg = renderIcon("NonExistentIcon");
    expect(svg).toBe("");
  });
});
