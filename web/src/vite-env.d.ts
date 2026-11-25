/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "api" = Chat AI uses POST /api/v1/chat; anything else = the in-browser mock. */
  readonly VITE_CHAT_BACKEND?: string;
  /** "firebase" = dev-only Google login. Ignored in production builds. */
  readonly VITE_AUTH_PROVIDER?: string;
}
