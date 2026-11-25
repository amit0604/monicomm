import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const HEX_COLOR = "/#[0-9a-fA-F]{3,8}\\b/";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // UI rule (PROJECT.md 6A): colors come from tokens.css, never hard-coded in components
      "no-restricted-syntax": [
        "error",
        {
          selector: `Literal[value=${HEX_COLOR}]`,
          message: "Use a design token (var(--...)) instead of a raw hex color.",
        },
        {
          selector: `TemplateElement[value.raw=${HEX_COLOR}]`,
          message: "Use a design token (var(--...)) instead of a raw hex color.",
        },
      ],
      // Air-gap rule: no remote URLs in front-end code
      "no-restricted-imports": ["error", { patterns: ["http://*", "https://*"] }],
    },
  },
);
