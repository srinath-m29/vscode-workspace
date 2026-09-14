/**
 * Reusable fetch client for Cloud IDE API.
 * Uses relative `/api/...` paths and includes HttpOnly session cookies.
 * Never exposes tokens or secrets to client-side code.
 */

import { AuthMeResponse } from '../types';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = endpoint.startsWith('/') ? endpoint : `/api/${endpoint}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include', // Includes HttpOnly session cookie
  });

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMessage = typeof errorJson.detail === 'string'
          ? errorJson.detail
          : JSON.stringify(errorJson.detail);
      }
    } catch {
      if (response.statusText) {
        errorMessage = response.statusText;
      }
    }
    throw new ApiError(errorMessage, response.status);
  }

  const text = await response.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export async function checkHealth(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>('/api/health');
}

export async function getMe(): Promise<AuthMeResponse> {
  return apiFetch<AuthMeResponse>('/api/auth/me');
}

export async function logout(): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>('/api/auth/logout', {
    method: 'POST',
  });
}

export function getLoginUrl(): string {
  return '/api/auth/login';
}
