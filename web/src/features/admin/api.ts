// Mirrors api/app/modules/admin/router.py and auth_methods.py. Secrets are sent, never received.
import { ApiError, request } from "../../lib/api";

export interface LLMView {
  provider: "ollama" | "gemini";
  base_url: string;
  model: string;
  gemini_model: string;
  key_source: "none" | "env" | "saved";
  saved: boolean;
}

export interface LLMForm extends Omit<LLMView, "key_source" | "saved"> {
  api_key: string | null; // null = keep the current key
}

export interface CheckResult {
  ok: boolean;
  error: "key_missing" | "key_rejected" | "model_not_found" | "rate_limited" | "unavailable" | null;
}

type ErrorCode = "key_missing" | "external_url" | "invalid" | "access" | "dev_only" | "failed";

export class AdminError extends Error {
  constructor(readonly code: ErrorCode) {
    super(code);
  }
}

function codeOf(status: number, detail: string | undefined): ErrorCode {
  if (detail === "dev_only") return detail;
  if (status === 401 || status === 403) return "access";
  if (status === 422) return "invalid";
  if (detail === "key_missing" || detail === "external_url") return detail;
  return "failed";
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  try {
    return await request<T>(url, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw e instanceof ApiError ? new AdminError(codeOf(e.status, e.detail)) : e;
  }
}

const LLM = "/api/v1/admin/llm";
export const llmApi = {
  read: () => call<LLMView>("GET", LLM),
  save: (form: LLMForm) => call<LLMView>("PUT", LLM, form),
  reset: () => call<LLMView>("DELETE", LLM),
  test: (form: LLMForm) => call<CheckResult>("POST", `${LLM}/test`, form),
};

// Login methods (LDAP, SSO). The view holds every setting except the secret.
export type AuthSection = "ldap" | "sso";
export type AuthValue = string | boolean;
export interface AuthView {
  [field: string]: AuthValue | undefined;
  enabled: boolean;
  saved: boolean;
  secret_source: "none" | "env" | "saved";
  callback_url?: string; // SSO: the address to register at the identity provider
}
export interface AuthTestResult {
  ok: boolean;
  error: string | null;
  user: { dn: string; role: string } | null; // LDAP: the looked-up test user
}

export const authApi = (section: AuthSection) => {
  const url = `/api/v1/admin/auth/${section}`;
  return {
    read: () => call<AuthView>("GET", url),
    save: (form: Record<string, AuthValue | null>) => call<AuthView>("PUT", url, form),
    reset: () => call<AuthView>("DELETE", url),
    test: (form: Record<string, AuthValue | null>) =>
      call<AuthTestResult>("POST", `${url}/test`, form),
  };
};
