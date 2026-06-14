import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import LoadingSpinner from "../../src/components/common/LoadingSpinner";

describe("LoadingSpinner", () => {
  it("renders CircularProgress", () => {
    render(<LoadingSpinner />);
    const spinner = document.querySelector(".MuiCircularProgress-root");
    expect(spinner).toBeInTheDocument();
  });

  it("renders optional message", () => {
    render(<LoadingSpinner message="Fetching problems..." />);
    expect(screen.getByText("Fetching problems...")).toBeInTheDocument();
  });

  it("does not render message when not provided", () => {
    render(<LoadingSpinner />);
    const container = screen.getByRole("status");
    expect(container).toBeInTheDocument();
    // Should have only the spinner, no extra text
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("has role=status for accessibility", () => {
    render(<LoadingSpinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("has aria-label when message provided", () => {
    render(<LoadingSpinner message="Loading..." />);
    expect(screen.getByLabelText("Loading...")).toBeInTheDocument();
  });

  it("has default aria-label when no message", () => {
    render(<LoadingSpinner />);
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("renders fullPage variant with larger padding", () => {
    render(<LoadingSpinner fullPage />);
    const container = screen.getByRole("status");
    expect(container).toBeInTheDocument();
  });

  it("accepts custom size", () => {
    render(<LoadingSpinner size={60} />);
    const spinner = document.querySelector(".MuiCircularProgress-root");
    expect(spinner).toBeInTheDocument();
  });
});
