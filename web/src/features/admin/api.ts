// Mirrors api/app/modules/admin/router.py. The API key is sent, never received.
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

type ErrorCode = "key_missing" | "external_url" | "invalid" | "access" | "failed";

export class AdminError extends Error {
  constructor(readonly code: ErrorCode) {
    super(code);
  }
}

function codeOf(status: number, detail: unknown): ErrorCode {
  if (status === 401 || status === 403) return "access";
  if (status === 422) return "invalid";
  if (detail === "key_missing" || detail === "external_url") return detail;
  return "failed";
}

async function call<T>(method: string, path = "", form?: LLMForm): Promise<T> {
  const res = await fetch(`/api/v1/admin/llm${path}`, {
    method,
    headers: form && { "content-type": "application/json" },
    body: form && JSON.stringify(form),
  });
  if (res.ok) return (await res.json()) as T;
  const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
  throw new AdminError(codeOf(res.status, body?.detail));
}

export const llmApi = {
  read: () => call<LLMView>("GET"),
  save: (form: LLMForm) => call<LLMView>("PUT", "", form),
  reset: () => call<LLMView>("DELETE"),
  test: (form: LLMForm) => call<CheckResult>("POST", "/test", form),
};
