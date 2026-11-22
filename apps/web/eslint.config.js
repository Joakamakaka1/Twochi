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

function upwardImports(layer) {
  const above = LAYERS.slice(0, LAYERS.indexOf(layer));
  if (above.length === 0) return [];
  return [
    {
      regex: String.raw`^(\.\./)+(${above.join("|")})(/|$)`,
      message: `${layer} cannot import ${above.join(" or ")}: imports go app -> features -> scene -> shared.`,
    },
  ];
}

function layerImports(layer) {
  return restrictImports([`src/${layer}/**/*.{ts,tsx}`], [deepImport, ...upwardImports(layer)]);
}

// A feature never imports another one: what they share goes down to shared or is composed in app.
// From a file N folders deep inside src/features/<name>/, climbing N levels and descending into
// anything is a sibling feature (or the features barrel).
const crossFeatureImports = [1, 2, 3, 4].map((depth) =>
  restrictImports(
    [`src/features/*/${"*/".repeat(depth - 1)}*.{ts,tsx}`],
    [
      deepImport,
      {
        regex: String.raw`^(\.\./){${depth}}[^.]`,
        message: "A feature cannot import another feature: move the shared part to shared or compose it in app.",
      },
      ...upwardImports("features"),
    ],
  ),
);

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
  ...crossFeatureImports,
  // Network (Arquitectura y convenciones, «Convenciones del front»): supabase-js only in the
  // auth feature, and fetch only behind the generated client in shared/api. The typescript-eslint
  // twin of the import rule, so it adds to the folder rules above instead of replacing them.
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/features/auth/**"],
    rules: {
      "@typescript-eslint/no-restricted-imports": [
        "error",
        { patterns: [{ regex: "^@supabase/", message: "supabase-js is only imported in features/auth." }] },
      ],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/shared/api/**"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "No fetch outside shared/api: use the generated client (useApi)." },
      ],
    },
  },
]);
