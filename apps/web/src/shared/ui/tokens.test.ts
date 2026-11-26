import { describe, expect, it } from "vitest";

// The style base (TWO-50): one tokens file, nothing hand-written elsewhere and a font
// the app serves itself. Read as text, so the rules hold for every stylesheet in src.
const TOKENS = "/src/shared/ui/tokens.css";
const FONTS = "/src/shared/ui/fonts/";

const stylesheets = import.meta.glob<string>("/src/**/*.css", { query: "?raw", import: "default", eager: true });
const fontFiles = Object.keys(import.meta.glob("/src/shared/ui/fonts/*"));
const licenses = import.meta.glob<string>("/src/shared/ui/fonts/OFL.txt", {
  query: "?raw",
  import: "default",
  eager: true,
});
const indexHtml = import.meta.glob<string>("/index.html", { query: "?raw", import: "default", eager: true });

// Colours and lengths (spaces, radii, sizes) written as literals. Unitless numbers, 0,
// percentages and viewport units stay allowed: they are proportions, not design values.
const HAND_WRITTEN = [
  /#[0-9a-f]{3,8}\b/gi,
  /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(/gi,
  /(?<![\w-])\d*\.?\d+(?:px|rem|em|ch|pt)\b/gi,
];

function handWritten(css: string): string[] {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return HAND_WRITTEN.flatMap((pattern) => withoutComments.match(pattern) ?? []);
}

// A url() or link that leaves the page's own origin.
const REMOTE = /url\(\s*["']?(?:[a-z]+:)?\/\/|@import\s+["'](?:[a-z]+:)?\/\/|href=["'](?:[a-z]+:)?\/\//gi;

function source(files: Record<string, string>, path: string): string {
  const text = files[path];
  if (text === undefined) throw new Error(`${path} is missing`);
  return text;
}

describe("style tokens", () => {
  it("spots a hand-written colour, radius or space", () => {
    expect(handWritten(".a { padding: 12px 0.5rem; color: #fff; border-radius: 2em; background: rgb(1 2 3) }")).toEqual(
      ["#fff", "rgb(", "12px", "0.5rem", "2em"],
    );
    expect(handWritten(".a { padding: var(--space-2); margin: 0; width: 100%; line-height: 1.4 }")).toEqual([]);
  });

  it("keeps every token in a single file of CSS variables", () => {
    expect(source(stylesheets, TOKENS)).toMatch(/:root\s*{[^}]*--color-[\w-]+:/);
  });

  it("lets no other stylesheet write a colour, radius or space by hand", () => {
    const others = Object.entries(stylesheets).filter(([path]) => path !== TOKENS);
    expect(others.length).toBeGreaterThan(0);
    for (const [path, css] of others) {
      expect({ path, values: handWritten(css) }).toEqual({ path, values: [] });
    }
  });

  it("serves its font from the app, with the OFL license next to it", () => {
    const fontUrl = /@font-face\s*{[^}]*src:\s*url\(["']?\.\/fonts\/([\w.-]+\.woff2)["']?\)/.exec(source(stylesheets, TOKENS));
    expect(fontUrl).not.toBeNull();
    expect(fontFiles).toContain(`${FONTS}${fontUrl?.[1] ?? ""}`);
    expect(source(licenses, `${FONTS}OFL.txt`)).toContain("SIL Open Font License, Version 1.1");
  });

  it("fetches no stylesheet or font from another host", () => {
    const pages = { ...stylesheets, ...indexHtml };
    expect(Object.keys(indexHtml)).toEqual(["/index.html"]);
    for (const [path, text] of Object.entries(pages)) {
      expect({ path, remote: text.match(REMOTE) ?? [] }).toEqual({ path, remote: [] });
    }
  });
});
