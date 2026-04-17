import type { GoogleLoginCredentials, AuthResponse } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'remote_control_token';

export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

export function logout(): void {
  removeToken();
}

export async function loginWithGoogle(credentials: GoogleLoginCredentials): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE}/api/auth/google`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Google login failed' }));
    throw new Error(error.detail || 'Google login failed');
  }

  const data: AuthResponse = await response.json();
  saveToken(data.access_token);
  return data;
}
