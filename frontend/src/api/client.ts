export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function detailFromPayload(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail !== undefined) return JSON.stringify(detail);
  }
  return `SirenGrid request failed (${status})`;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, credentials: 'include' });
  } catch {
    throw new ApiError(0, 'Backend unavailable. Check that the SirenGrid API is running.');
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      if (response.ok) throw new ApiError(response.status, 'Backend returned an invalid response.');
    }
  }
  if (!response.ok) throw new ApiError(response.status, detailFromPayload(payload, response.status));
  return payload as T;
}

export function requireArray<T>(value: unknown, label: string): T[] {
  if (!Array.isArray(value)) throw new ApiError(200, `Backend returned an invalid ${label} payload.`);
  return value as T[];
}

export function requireObject<T extends object>(value: unknown, label: string): T {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ApiError(200, `Backend returned an invalid ${label} payload.`);
  }
  return value as T;
}
