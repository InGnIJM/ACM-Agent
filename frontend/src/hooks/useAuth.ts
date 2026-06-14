// ============================================================
// Auth hook — exposes user state, login, register, logout.
// Pairs with the auth service and stores JWT tokens in localStorage.
// ============================================================

import { useState, useEffect, useCallback } from "react";
import * as authApi from "../services/auth";
import type { User } from "../types/user";

export interface UseAuthReturn {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: typeof authApi.register;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
  tokenStatus: "logged_in" | "expired" | "none";
}

/** Decode JWT payload without verification to check expiry */
function getTokenStatus(): "logged_in" | "expired" | "none" {
  const token = localStorage.getItem("access_token");
  if (!token) return "none";
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const now = Date.now() / 1000;
    return payload.exp && payload.exp > now ? "logged_in" : "expired";
  } catch {
    return "none";
  }
}

export default function useAuth(): UseAuthReturn {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    // Skip auto-fetch on public pages to avoid 401 noise
    if (window.location.pathname.startsWith("/login") || window.location.pathname.startsWith("/register")) {
      setLoading(false);
      return;
    }
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const me = await authApi.getMe();
      setUser(me);
    } catch {
      // Token expired or invalid — clear it
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const login = useCallback(async (username: string, password: string) => {
    await authApi.login({ username, password });
    const me = await authApi.getMe();
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  return {
    user,
    loading,
    login,
    register: authApi.register,
    logout,
    isAuthenticated: !!user,
    tokenStatus: getTokenStatus(),
  };
}
