// ============================================================
// Login page tests
// ============================================================

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Login from "../../src/pages/Login";

// ---- mocks ----

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockLogin = vi.fn();
const mockUseAuthReturn = {
  user: null,
  loading: false,
  login: mockLogin,
  register: vi.fn(),
  logout: vi.fn(),
  isAuthenticated: false,
};

vi.mock("../../src/hooks/useAuth", () => ({
  default: () => mockUseAuthReturn,
}));

// ---- helpers ----

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Login />
    </MemoryRouter>
  );
}

// ---- tests ----

describe("Login", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthReturn.user = null;
    mockUseAuthReturn.isAuthenticated = false;
    mockUseAuthReturn.loading = false;
    mockLogin.mockReset();
    mockNavigate.mockReset();
  });

  // ============================================================
  // Render
  // ============================================================

  it("renders the login form", () => {
    renderLogin();

    expect(screen.getByText("ACM Agent")).toBeInTheDocument();
    expect(screen.getByLabelText("用户名")).toBeInTheDocument();
    expect(screen.getByLabelText("密码")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
  });

  it("renders the register link", () => {
    renderLogin();

    expect(screen.getByText("还没有账号？")).toBeInTheDocument();
    const registerLink = screen.getByText("立即注册");
    expect(registerLink).toBeInTheDocument();
    expect(registerLink.closest("a")).toHaveAttribute("href", "/register");
  });

  it("renders the subtitle text", () => {
    renderLogin();

    expect(
      screen.getByText("登录你的算法训练账号")
    ).toBeInTheDocument();
  });

  // ============================================================
  // Error: empty fields
  // ============================================================

  it("shows error when submitting with empty username", async () => {
    renderLogin();

    const submitBtn = screen.getByRole("button", { name: "登录" });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("请输入用户名和密码")).toBeInTheDocument();
    });
  });

  it("shows error when submitting with empty password only", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "testuser");
    // Leave password empty
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("请输入用户名和密码")).toBeInTheDocument();
    });
  });

  it("shows error when submitting with only whitespace", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "   ");
    await user.type(screen.getByLabelText("密码"), "   ");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("请输入用户名和密码")).toBeInTheDocument();
    });
  });

  // ============================================================
  // Error: login failure
  // ============================================================

  it("displays error message on login failure", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValueOnce(new Error("Invalid credentials"));
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "baduser");
    await user.type(screen.getByLabelText("密码"), "wrongpass");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
    expect(mockLogin).toHaveBeenCalledWith("baduser", "wrongpass");
  });

  it("displays fallback error message on non-Error rejection", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValueOnce("some string error");
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "user");
    await user.type(screen.getByLabelText("密码"), "pass");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(
        screen.getByText("登录失败，请检查用户名和密码")
      ).toBeInTheDocument();
    });
  });

  it("clears previous error on new submission attempt", async () => {
    const user = userEvent.setup();
    // First attempt fails
    mockLogin.mockRejectedValueOnce(new Error("Bad"));
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "user");
    await user.type(screen.getByLabelText("密码"), "pass");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("Bad")).toBeInTheDocument();
    });

    // Second attempt succeeds
    mockLogin.mockResolvedValueOnce(undefined);
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      // Error should be cleared
      expect(screen.queryByText("Bad")).toBeNull();
    });
  });

  // ============================================================
  // Success: redirect
  // ============================================================

  it("redirects to / on successful login", async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValueOnce(undefined);
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "gooduser");
    await user.type(screen.getByLabelText("密码"), "goodpass");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("gooduser", "goodpass");
      expect(mockNavigate).toHaveBeenCalledWith("/", { replace: true });
    });
  });

  it("trims whitespace from username before login", async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValueOnce(undefined);
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "  myuser  ");
    await user.type(screen.getByLabelText("密码"), "mypass");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("myuser", "mypass");
    });
  });

  // ============================================================
  // Already authenticated
  // ============================================================

  it("redirects immediately when already authenticated", () => {
    mockUseAuthReturn.isAuthenticated = true;
    mockUseAuthReturn.user = { id: 1, username: "admin", role: "admin" } as any;

    renderLogin();

    expect(mockNavigate).toHaveBeenCalledWith("/", { replace: true });
  });

  // ============================================================
  // Loading state
  // ============================================================

  it("disables submit button while submitting", async () => {
    const user = userEvent.setup();
    // Never resolves so we can check the loading state
    mockLogin.mockImplementation(
      () => new Promise(() => { /* pending forever */ })
    );
    renderLogin();

    await user.type(screen.getByLabelText("用户名"), "user");
    await user.type(screen.getByLabelText("密码"), "pass");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      // The button should now show a CircularProgress instead of text
      expect(
        screen.queryByRole("button", { name: "登录" })
      ).toBeNull();
    });
  });
});
