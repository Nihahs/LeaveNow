import type { CommuteLog, CommuteLogInput, Recommendation, RouteConfig } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getRoute(): Promise<RouteConfig> {
  return request<RouteConfig>("/route");
}

export function updateRoute(route: Omit<RouteConfig, "id" | "timezone">): Promise<RouteConfig> {
  return request<RouteConfig>("/route", {
    method: "PUT",
    body: JSON.stringify(route),
  });
}

export function getRecommendation(route: RouteConfig, date: string): Promise<Recommendation> {
  const params = new URLSearchParams({
    date,
    windowStart: route.defaultWindowStart,
    windowEnd: route.defaultWindowEnd,
    intervalMinutes: String(route.defaultIntervalMinutes),
  });
  return request<Recommendation>(`/recommendation?${params.toString()}`);
}

export function createCommuteLog(input: CommuteLogInput): Promise<CommuteLog> {
  return request<CommuteLog>("/commute-log", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getCommuteLogs(): Promise<CommuteLog[]> {
  return request<CommuteLog[]>("/commute-log?limit=5");
}
