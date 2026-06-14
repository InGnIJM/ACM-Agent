// ============================================================
// Auth context — provides user, team, and auth actions
// ============================================================

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import type { User, Role } from "../../types/user";
import type { Team } from "../../types/team";
import { getMe } from "../../services/auth";

// ---- types ----

export interface AuthState {
  user: User | null;
  team: Team | null;
  loading: boolean;
  login: (user: User) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
  setTeam: (team: Team | null) => void;
}

// ---- context ----

const AuthContext = createContext<AuthState>({
  user: null,
  team: null,
  loading: true,
  login: () => {},
  logout: () => {},
  refreshUser: async () => {},
  setTeam: () => {},
});

// ---- provider ----

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [loading, setLoading] = useState(true);

  // Try to restore session on mount
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    getMe()
      .then((u) => {
        if (!cancelled) {
          setUser(u);
        }
      })
      .catch(() => {
        // Token invalid or expired without refresh — clear it
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback((u: User) => {
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setTeam(null);
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const u = await getMe();
      setUser(u);
    } catch {
      // Silently fail — the interceptor will handle 401 redirect
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, team, loading, login, logout, refreshUser, setTeam }}>
      {children}
    </AuthContext.Provider>
  );
}

// ---- hook ----

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

// ---- helpers ----

export function isAdmin(role?: Role): boolean {
  return role === "admin";
}
