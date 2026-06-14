// ============================================================
// Axios instance with auth interceptors
// ============================================================

import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import type { ApiError } from "../types/api";

// Extend the request config to track retry state
interface RetryableRequest extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

const api = axios.create({
  baseURL: "/api",
  timeout: 10_000,
  headers: { "Content-Type": "application/json" },
});

// ---- helpers ----

function getAccessToken(): string | null {
  return localStorage.getItem("access_token");
}

function getRefreshToken(): string | null {
  return localStorage.getItem("refresh_token");
}

function storeTokens(access: string, refresh: string): void {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

function clearTokens(): void {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

// ---- request interceptor ----

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ---- response interceptor ----

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: AxiosError<ApiError>) => void;
}> = [];

function processQueue(error: AxiosError<ApiError> | null, token: string | null) {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else if (token) {
      promise.resolve(token);
    }
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as RetryableRequest;
    if (!originalRequest) {
      return Promise.reject(error);
    }

    // Only handle 401 and not already retried
    if (error.response?.status !== 401 || originalRequest._retried) {
      return Promise.reject(error);
    }

    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      clearTokens();
      if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/register")) {
        window.location.href = "/login";
      }
      return Promise.reject(error);
    }

    if (isRefreshing) {
      // Queue this request until the refresh completes
      return new Promise<void>((resolve, reject) => {
        failedQueue.push({
          resolve: (token: string) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(api(originalRequest));
          },
          reject: (err) => {
            reject(err);
          },
        });
      });
    }

    originalRequest._retried = true;
    isRefreshing = true;

    try {
      const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
        "/api/auth/refresh",
        { refresh_token: refreshToken },
      );

      const newAccess = data.access_token;
      const newRefresh = data.refresh_token ?? refreshToken;
      storeTokens(newAccess, newRefresh);

      processQueue(null, newAccess);

      originalRequest.headers.Authorization = `Bearer ${newAccess}`;
      return api(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError as AxiosError<ApiError>, null);
      clearTokens();
      if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/register")) {
        window.location.href = "/login";
      }
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  },
);

export default api;
