export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
  timeoutMs?: number;
}

/** Transport only. Paths and wire schemas must come from the backend owner. */
export function createApiClient(options: ApiClientOptions = {}) {
  const configured = (options.baseUrl ?? process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/$/, "");
  return {
    async request<T>(contractPath: string, init: RequestInit = {}): Promise<T> {
      if (!configured) throw new ApiError("The Flask API URL has not been configured.", 0, "API_NOT_CONFIGURED");
      let base: URL;
      try { base = new URL(configured); } catch { throw new ApiError("The Flask API URL must be an absolute HTTP or HTTPS URL.", 0, "INVALID_API_URL"); }
      if (base.protocol !== "https:" && base.protocol !== "http:") throw new ApiError("The Flask API URL must use HTTP or HTTPS.", 0, "INVALID_API_URL");
      if (!contractPath.startsWith("/") || contractPath.startsWith("//") || contractPath.includes("..") || /^[a-z]+:/i.test(contractPath)) throw new ApiError("Use a relative path from the approved API contract.", 0, "INVALID_CONTRACT_PATH");
      const configuredPrefix = base.pathname.replace(/\/+$/, "");
      if (configuredPrefix && configuredPrefix !== "/api/v1") {
        throw new ApiError("Set the Flask API URL to its origin or its /api/v1 base URL.", 0, "INVALID_API_NAMESPACE");
      }
      // Accept either https://flask.example or https://flask.example/api/v1,
      // while keeping every request inside the approved versioned namespace.
      const prefix = configuredPrefix || "/api/v1";
      const path = contractPath === prefix || contractPath.startsWith(`${prefix}/`)
        ? contractPath
        : `${prefix}${contractPath}`;
      const url = new URL(path, base.origin);
      if (!url.pathname.startsWith("/api/v1/")) throw new ApiError("The approved Flask API must use the /api/v1 namespace.", 0, "INVALID_API_NAMESPACE");
      const controller = new AbortController();
      const abort = () => controller.abort();
      init.signal?.addEventListener("abort", abort, { once: true });
      if (init.signal?.aborted) controller.abort();
      const timer = setTimeout(abort, options.timeoutMs ?? 15000);
      const headers = new Headers(init.headers);
      headers.set("Accept", "application/json");
      if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
      const token = options.getAccessToken?.();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      try {
        const response = await fetch(url, { ...init, headers, credentials: "include", signal: controller.signal });
        const isJson = response.headers.get("content-type")?.includes("application/json");
        const body: unknown = response.status === 204 ? undefined : isJson ? await response.json() : undefined;
        if (!response.ok) {
          const data = body && typeof body === "object" ? body as Record<string, unknown> : {};
          const message = typeof data.message === "string" ? data.message : typeof data.error === "string" ? data.error : "The request could not be completed. Please try again.";
          throw new ApiError(message, response.status, typeof data.code === "string" ? data.code : undefined);
        }
        if (response.status !== 204 && !isJson) throw new ApiError("The API returned an unexpected response format.", response.status, "INVALID_RESPONSE");
        return body as T;
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (controller.signal.aborted) throw new ApiError(init.signal?.aborted ? "The request was cancelled." : "The request timed out. Please try again.", 0, "REQUEST_ABORTED");
        throw new ApiError("Unable to reach the backend. Check your connection and try again.", 0, "NETWORK_ERROR");
      } finally {
        clearTimeout(timer);
        init.signal?.removeEventListener("abort", abort);
      }
    },
  };
}
