// ============================================================
// User / Auth types
// ============================================================

export type Role = "admin" | "user";

export interface PlatformAccount {
  platform: string;
  handle: string;
  verified: boolean;
}

export interface User {
  id: number;
  username: string;
  email: string;
  nickname?: string;
  avatar_url?: string;
  role: Role;
  coins: number;
  credits: number;
  bio?: string;
  platforms: PlatformAccount[];
  created_at: string;
  updated_at: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  nickname?: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface UserUpdate {
  nickname?: string;
  avatar_url?: string;
  bio?: string;
}

export interface BindPlatformRequest {
  platform: string;
  handle: string;
}
