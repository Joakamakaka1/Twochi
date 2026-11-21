import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

// Front folders, outermost first: each may import only the ones after it.
const LAYERS = ["app", "features", "scene", "shared"];

const deepImport = {
  regex: String.raw`^(\.\.?/)+(${LAYERS.join("|")})/`,
  message: "Import the folder through its index.ts, not its internal files.",
};

function restrictImports(files, patterns) {
  return { files, rules: { "no-restricted-imports": ["error", { patterns }] } };
}

function layerImports(layer) {
  const above = LAYERS.slice(0, LAYERS.indexOf(layer));
  const patterns = [deepImport];
  if (above.length > 0) {
    patterns.push({
      regex: String.raw`^(\.\./)+(${above.join("|")})(/|$)`,
      message: `${layer} cannot import ${above.join(" or ")}: imports go app -> features -> scene -> shared.`,
    });
  }
  return restrictImports([`src/${layer}/**/*.{ts,tsx}`], patterns);
}

export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      reactHooks.configs.flat["recommended-latest"],
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  // Entry files at the root of src, such as main.tsx.
  restrictImports(["src/*.{ts,tsx}"], [deepImport]),
  ...LAYERS.map(layerImports),
]);
