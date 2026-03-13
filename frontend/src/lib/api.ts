const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("token") : null;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  if (res.status === 204) return {} as T;
  return res.json();
}

// Auth
export const auth = {
  login: (username: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>(
      "/api/v1/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
    ),
  me: () => request<import("@/types/api").User>("/api/v1/me"),
};

// Groups
export const groups = {
  list: () =>
    request<import("@/types/api").Group[]>("/api/v1/groups"),
  create: (data: { name: string; description?: string }) =>
    request<import("@/types/api").Group>("/api/v1/groups", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Fields
export const fields = {
  list: (groupId?: string) => {
    const params = groupId ? `?group_id=${groupId}` : "";
    return request<import("@/types/api").FieldListResponse>(
      `/api/v1/fields${params}`,
    );
  },
  get: (id: string) =>
    request<import("@/types/api").Field>(`/api/v1/fields/${id}`),
  create: (data: {
    name: string;
    group_id: string;
    geometry?: GeoJSON.Geometry;
  }) =>
    request<import("@/types/api").Field>("/api/v1/fields", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Record<string, unknown>) =>
    request<import("@/types/api").Field>(`/api/v1/fields/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    request<void>(`/api/v1/fields/${id}`, { method: "DELETE" }),
};

// Geometry
export const geometry = {
  area: (geom: GeoJSON.Geometry) =>
    request<{ area_acres: number; area_sq_meters: number }>(
      "/api/v1/geometry/area",
      { method: "POST", body: JSON.stringify({ geometry: geom }) },
    ),
};

export { ApiError };
