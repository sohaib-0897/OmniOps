const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

class ApiClient {
  private getToken(): string | null {
    if (typeof window !== "undefined") {
      return localStorage.getItem("omniops_token");
    }
    return null;
  }

  public setToken(token: string) {
    if (typeof window !== "undefined") {
      localStorage.setItem("omniops_token", token);
    }
  }

  public clearToken() {
    if (typeof window !== "undefined") {
      localStorage.removeItem("omniops_token");
    }
  }

  public async request<T>(
    endpoint: string,
    options: RequestInit = {}
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

    const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      this.clearToken();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        // window.location.href = "/";
      }
    }

    let data: any;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok || !data?.success) {
      const errorMsg =
        data?.error?.message ||
        data?.detail ||
        (typeof data === "string" ? data : `HTTP Error ${response.status}`);
      throw new Error(errorMsg);
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
}

export const apiClient = new ApiClient();
