// One way to call the Monicomm API: JSON in, JSON out, any non-2xx answer as an ApiError.

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** The server's reason, when it sent one (e.g. why a parse failed). */
    readonly detail?: string,
  ) {
    super(message);
  }
}

// FastAPI sends {"detail": "..."}; some routes nest it: {"detail": {"detail": "..."}}.
function detailOf(body: unknown): string | undefined {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  const inner = (d as { detail?: unknown } | null)?.detail;
  return typeof inner === "string" ? inner : undefined;
}

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    throw new ApiError(res.status, `Request failed (${res.status})`, detailOf(body));
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
