// ============================================================
// Users service
// ============================================================

import api from "./api";
import type { User, UserUpdate, BindPlatformRequest } from "../types/user";
import type { PaginatedResponse } from "../types/api";

const USERS = "/users";

export interface UserListQuery {
  page?: number;
  page_size?: number;
  search?: string;
  role?: string;
  sort_by?: string;
  order?: "asc" | "desc";
}

export async function getUsers(query: UserListQuery = {}): Promise<PaginatedResponse<User>> {
  const resp = await api.get<PaginatedResponse<User>>(USERS, { params: query });
  return resp.data;
}

export async function getUser(id: number): Promise<User> {
  const resp = await api.get<User>(`${USERS}/${id}`);
  return resp.data;
}

export async function updateUser(id: number, data: UserUpdate): Promise<User> {
  const resp = await api.patch<User>(`${USERS}/${id}`, data);
  return resp.data;
}

export async function deleteUser(id: number): Promise<void> {
  await api.delete(`${USERS}/${id}`);
}

export async function bindPlatform(userId: number, data: BindPlatformRequest): Promise<User> {
  const resp = await api.post<User>(`${USERS}/${userId}/platforms`, data);
  return resp.data;
}

export async function unbindPlatform(userId: number, platform: string): Promise<User> {
  const resp = await api.delete<User>(`${USERS}/${userId}/platforms/${platform}`);
  return resp.data;
}
