// ============================================================
// Auth service
// ============================================================

import api from "./api";
import type { User, LoginRequest, RegisterRequest, TokenPair } from "../types/user";

const AUTH = "/auth";

export async function login(data: LoginRequest): Promise<TokenPair> {
  const resp = await api.post<TokenPair>(`${AUTH}/login`, {
    username: data.username,
    password: data.password,
  });

  localStorage.setItem("access_token", resp.data.access_token);
  localStorage.setItem("refresh_token", resp.data.refresh_token);

  return resp.data;
}

export async function register(data: RegisterRequest): Promise<User> {
  const resp = await api.post<User>(`${AUTH}/register`, data);
  return resp.data;
}

export async function getMe(): Promise<User> {
  const resp = await api.get<User>(`${AUTH}/me`);
  return resp.data;
}

export async function refreshToken(refreshToken: string): Promise<TokenPair> {
  const resp = await api.post<TokenPair>(`${AUTH}/refresh`, {
    refresh_token: refreshToken,
  });

  localStorage.setItem("access_token", resp.data.access_token);
  localStorage.setItem("refresh_token", resp.data.refresh_token);

  return resp.data;
}

export async function logout(): Promise<void> {
  try {
    await api.post(`${AUTH}/logout`);
  } finally {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }
}
