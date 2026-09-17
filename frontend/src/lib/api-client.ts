// The standalone dev server has no API reverse proxy; production uses Caddy
// and the same-origin /api/v1 path.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NODE_ENV === "development"
    ? "http://localhost:8000/api/v1"
    : "/api/v1");

class ApiClient {
  private accessToken: string | null = null;
  private refreshPromise: Promise<boolean> | null = null;
  private getToken(): string | null {
    return this.accessToken;
  }

  public setToken(token: string) {
    this.accessToken = token;
  }

  public clearToken() {
    this.accessToken = null;
  }

  public getAccessToken() {
    return this.accessToken;
  }

  private async fetchWithTimeout(
    input: RequestInfo | URL,
    init: RequestInit = {},
    timeoutMs = 10000,
  ) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(input, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  public async refresh(): Promise<boolean> {
    if (this.refreshPromise) return this.refreshPromise;
    this.refreshPromise = (async () => {
      try {
        const response = await this.fetchWithTimeout(`${API_BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        });
        const body = await response.json();
        if (!response.ok || !body?.success) {
          this.clearToken();
          return false;
        }
        this.setToken(body.data.token.access_token);
        return true;
      } catch {
        this.clearToken();
        return false;
      } finally {
        this.refreshPromise = null;
      }
    })();
    return this.refreshPromise;
  }

  public async request<T>(
    endpoint: string,
    options: RequestInit = {},
  ): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    const url = endpoint.startsWith("http")
      ? endpoint
      : `${API_BASE}${endpoint}`;
    let response = await this.fetchWithTimeout(url, {
      ...options,
      headers,
      credentials: "include",
    });

    const refreshable = ![
      "/auth/refresh",
      "/auth/login",
      "/auth/register",
      "/auth/logout",
    ].includes(endpoint);
    if (response.status === 401 && refreshable && (await this.refresh())) {
      headers["Authorization"] = `Bearer ${this.getToken()}`;
      response = await this.fetchWithTimeout(url, {
        ...options,
        headers,
        credentials: "include",
      });
    }

    let data: any;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok || !data?.success) {
      if (
        response.status === 401 &&
        refreshable &&
        typeof window !== "undefined"
      ) {
        this.clearToken();
        window.location.assign("/?session=expired");
      }
      const errorMsg =
        data?.error?.message ||
        (typeof data?.detail === "string" ? data.detail : null) ||
        (typeof data === "string" ? data : `HTTP Error ${response.status}`);
      const rawDetails = Array.isArray(data?.error?.details)
        ? data.error.details
        : Array.isArray(data?.detail)
          ? data.detail
          : [];
      const validationDetails = rawDetails.length
        ? rawDetails
            .map((detail: any) => {
              const location = Array.isArray(detail?.loc)
                ? detail.loc.filter(Boolean).join(" → ")
                : "";
              const message = detail?.msg || detail?.message || detail;
              return location ? `${location}: ${String(message)}` : String(message);
            })
            .filter(Boolean)
            .join("; ")
        : "";
      const detailedError = validationDetails
        ? `${errorMsg}: ${validationDetails}`
        : errorMsg;
      const requestId =
        data?.meta?.request_id || response.headers.get("X-Request-ID");
      throw new Error(
        requestId
          ? `${detailedError} (Request ${String(requestId).slice(0, 100)})`
          : detailedError,
      );
    }

    return data.data as T;
  }

  public get<T>(endpoint: string) {
    return this.request<T>(endpoint, { method: "GET" });
  }

  public post<T>(endpoint: string, body?: any) {
    const isFormData = body instanceof FormData;
    return this.request<T>(endpoint, {
      method: "POST",
      body: isFormData ? body : JSON.stringify(body),
    });
  }

  public delete<T>(endpoint: string) {
    return this.request<T>(endpoint, { method: "DELETE" });
  }

  public async logout() {
    try {
      await this.post("/auth/logout");
    } finally {
      this.clearToken();
    }
  }
}

export const apiClient = new ApiClient();
