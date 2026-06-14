import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import VerdictBadge from "../../src/components/common/VerdictBadge";

describe("VerdictBadge", () => {
  it("renders Accepted for 'accepted' status", () => {
    render(<VerdictBadge status="accepted" />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("renders OK for 'ok' status", () => {
    render(<VerdictBadge status="ok" />);
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("renders Wrong Answer for 'wrong_answer'", () => {
    render(<VerdictBadge status="wrong_answer" />);
    expect(screen.getByText("Wrong Answer")).toBeInTheDocument();
  });

  it("renders WA for 'wa'", () => {
    render(<VerdictBadge status="wa" />);
    expect(screen.getByText("WA")).toBeInTheDocument();
  });

  it("renders Time Limit for 'time_limit'", () => {
    render(<VerdictBadge status="time_limit" />);
    expect(screen.getByText("Time Limit")).toBeInTheDocument();
  });

  it("renders TLE for 'tle'", () => {
    render(<VerdictBadge status="tle" />);
    expect(screen.getByText("TLE")).toBeInTheDocument();
  });

  it("renders Memory Limit for 'memory_limit'", () => {
    render(<VerdictBadge status="memory_limit" />);
    expect(screen.getByText("Memory Limit")).toBeInTheDocument();
  });

  it("renders MLE for 'mle'", () => {
    render(<VerdictBadge status="mle" />);
    expect(screen.getByText("MLE")).toBeInTheDocument();
  });

  it("renders Runtime Error for 'runtime_error'", () => {
    render(<VerdictBadge status="runtime_error" />);
    expect(screen.getByText("Runtime Error")).toBeInTheDocument();
  });

  it("renders RE for 're'", () => {
    render(<VerdictBadge status="re" />);
    expect(screen.getByText("RE")).toBeInTheDocument();
  });

  it("renders Compile Error for 'compilation_error'", () => {
    render(<VerdictBadge status="compilation_error" />);
    expect(screen.getByText("Compile Error")).toBeInTheDocument();
  });

  it("renders CE for 'ce'", () => {
    render(<VerdictBadge status="ce" />);
    expect(screen.getByText("CE")).toBeInTheDocument();
  });

  it("renders Pending for 'pending'", () => {
    render(<VerdictBadge status="pending" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders raw status for unknown verdict (fallback)", () => {
    render(<VerdictBadge status="unknown_verdict" />);
    expect(screen.getByText("unknown_verdict")).toBeInTheDocument();
  });

  it("is case-insensitive", () => {
    render(<VerdictBadge status="ACCEPTED" />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("trims whitespace", () => {
    render(<VerdictBadge status="  ok  " />);
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("renders medium size when specified", () => {
    render(<VerdictBadge status="accepted" size="medium" />);
    const chip = screen.getByText("Accepted").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("renders outlined variant", () => {
    render(<VerdictBadge status="accepted" variant="outlined" />);
    const chip = screen.getByText("Accepted").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("maps accepted to success color", () => {
    render(<VerdictBadge status="accepted" />);
    const chip = screen.getByText("Accepted").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("maps wrong_answer to error color", () => {
    render(<VerdictBadge status="wrong_answer" />);
    const chip = screen.getByText("Wrong Answer").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });

  it("maps time_limit to warning color", () => {
    render(<VerdictBadge status="time_limit" />);
    const chip = screen.getByText("Time Limit").closest(".MuiChip-root");
    expect(chip).toBeInTheDocument();
  });
});
