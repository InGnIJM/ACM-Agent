// ============================================================
// API service tests — Axios interceptors
// ============================================================

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import api from "../../src/services/api";

// ---- helpers ----

/** Access the first request interceptor fulfilled handler */
function getRequestFulfilledHandler() {
  const handlers = (api.interceptors.request as any).handlers as Array<{
    fulfilled: (config: any) => any;
    rejected: (error: any) => any;
  }>;
  return handlers[0]?.fulfilled;
}

/** Access the first response interceptor rejected handler */
function getResponseRejectedHandler() {
  const handlers = (api.interceptors.response as any).handlers as Array<{
    fulfilled: (response: any) => any;
    rejected: (error: any) => any;
  }>;
  return handlers[0]?.rejected;
}

/** Create a minimal Axios-style error object */
function createAxiosError(overrides: Record<string, unknown> = {}) {
  return {
    isAxiosError: true,
    response: { status: 200, data: {} },
    config: { headers: {} as Record<string, string> },
    message: "",
    ...overrides,
  };
}

// ============================================================
// Tests
// ============================================================

describe("API request interceptor", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("is registered on the api instance", () => {
    const handlers = (api.interceptors.request as any).handlers;
    expect(handlers).toBeDefined();
    expect(handlers.length).toBeGreaterThan(0);
  });

  it("adds Bearer token to Authorization header when access_token exists", () => {
    localStorage.setItem("access_token", "my-jwt-token-value");

    const handler = getRequestFulfilledHandler();
    expect(handler).toBeDefined();

    const config = handler({ headers: {} });

    expect(config.headers.Authorization).toBe("Bearer my-jwt-token-value");
  });

  it("does not add Authorization header when no access_token in localStorage", () => {
    const handler = getRequestFulfilledHandler();
    expect(handler).toBeDefined();

    const config = handler({ headers: {} });

    expect(config.headers.Authorization).toBeUndefined();
  });

  it("preserves existing headers when adding token", () => {
    localStorage.setItem("access_token", "tok123");

    const handler = getRequestFulfilledHandler();
    const config = handler({
      headers: { "Content-Type": "application/json", "X-Custom": "value" },
    });

    expect(config.headers.Authorization).toBe("Bearer tok123");
    expect(config.headers["Content-Type"]).toBe("application/json");
    expect(config.headers["X-Custom"]).toBe("value");
  });

  it("handles empty access_token gracefully", () => {
    localStorage.setItem("access_token", "");

    const handler = getRequestFulfilledHandler();
    const config = handler({ headers: {} });

    // Empty string is falsy, so no header should be added
    expect(config.headers.Authorization).toBeUndefined();
  });

  it("overwrites existing Authorization header with token", () => {
    localStorage.setItem("access_token", "new-token");

    const handler = getRequestFulfilledHandler();
    const config = handler({
      headers: { Authorization: "Bearer old-token" },
    });

    expect(config.headers.Authorization).toBe("Bearer new-token");
  });

  it("returns config object unchanged when token is absent", () => {
    const handler = getRequestFulfilledHandler();

    const input = { headers: { "x-test": "y" }, url: "/test" };
    const output = handler(input);

    expect(output).toBe(input); // Same reference
  });
});

// ============================================================
// Response interceptor
// ============================================================

describe("API response interceptor", () => {
  let originalLocation: Location;

  beforeEach(() => {
    localStorage.clear();
    // Mock window.location for redirect assertions
    originalLocation = window.location;
    delete (window as any).location;
    (window as any).location = { href: "" };
  });

  afterEach(() => {
    localStorage.clear();
    (window as any).location = originalLocation;
  });

  it("is registered on the api instance", () => {
    const handlers = (api.interceptors.response as any).handlers;
    expect(handlers).toBeDefined();
    expect(handlers.length).toBeGreaterThan(0);
  });

  it("has a fulfilled handler that passes through successful responses", () => {
    const handlers = (api.interceptors.response as any).handlers as Array<{
      fulfilled: (response: any) => any;
      rejected: (error: any) => any;
    }>;
    const fulfilled = handlers[0]?.fulfilled;

    const response = { data: "ok", status: 200 };
    expect(fulfilled(response)).toBe(response);
  });

  // ---- 401 handling ----

  it("clears tokens and redirects on 401 without refresh_token", async () => {
    localStorage.setItem("access_token", "expired");
    // No refresh_token set

    const rejected = getResponseRejectedHandler();
    const error = createAxiosError({
      response: { status: 401, data: { detail: "Token expired" } },
      config: { headers: {} },
    });

    try {
      await rejected(error);
    } catch (e) {
      // Expected to reject
    }

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect((window as any).location.href).toBe("/login");
  });

  it("rejects with the original error on 401", async () => {
    localStorage.setItem("access_token", "expired");

    const rejected = getResponseRejectedHandler();
    const error = createAxiosError({
      response: { status: 401, data: { detail: "Expired" } },
      config: { headers: {} },
    });

    await expect(rejected(error)).rejects.toBeDefined();
  });

  it("does not handle non-401 errors", async () => {
    const rejected = getResponseRejectedHandler();
    const error = createAxiosError({
      response: { status: 500, data: { detail: "Server error" } },
      config: { headers: {} },
    });

    await expect(rejected(error)).rejects.toBe(error);
    // Should NOT clear tokens for non-401
    expect(localStorage.getItem("access_token")).toBeNull(); // Was never set
  });

  it("does not retry a request that was already retried", async () => {
    localStorage.setItem("refresh_token", "valid-refresh");

    const rejected = getResponseRejectedHandler();
    const error = createAxiosError({
      response: { status: 401, data: {} },
      config: { headers: {}, _retried: true },
    });

    // Should not attempt refresh; just reject
    await expect(rejected(error)).rejects.toBeDefined();
  });

  it("rejects when error has no config property", async () => {
    const rejected = getResponseRejectedHandler();
    const error = { isAxiosError: true, response: { status: 401 } };

    await expect(rejected(error)).rejects.toBeDefined();
  });

  // ---- 403 handling ----

  it("passes through 403 errors without clearing tokens", async () => {
    localStorage.setItem("access_token", "good-token");

    const rejected = getResponseRejectedHandler();
    const error = createAxiosError({
      response: { status: 403, data: { detail: "Forbidden" } },
      config: { headers: {} },
    });

    await expect(rejected(error)).rejects.toBeDefined();
    // Tokens should NOT be cleared for 403
    expect(localStorage.getItem("access_token")).toBe("good-token");
  });
});
