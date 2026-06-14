import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ConfirmDialog from "../../src/components/common/ConfirmDialog";

describe("ConfirmDialog", () => {
  it("does not render when closed", () => {
    render(
      <ConfirmDialog
        open={false}
        title="Delete Item"
        content="Are you sure?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.queryByText("Delete Item")).not.toBeInTheDocument();
  });

  it("renders when open", () => {
    render(
      <ConfirmDialog
        open
        title="Delete Item"
        content="Are you sure?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText("Delete Item")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("renders confirm and cancel buttons with default labels", () => {
    render(
      <ConfirmDialog
        open
        title="Delete"
        content="Proceed?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("renders custom button labels", () => {
    render(
      <ConfirmDialog
        open
        title="Confirm"
        content="Proceed?"
        confirmLabel="Yes, delete"
        cancelLabel="No, keep"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText("Yes, delete")).toBeInTheDocument();
    expect(screen.getByText("No, keep")).toBeInTheDocument();
  });

  it("calls onConfirm when confirm button clicked", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Delete"
        content="Proceed?"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when cancel button clicked", () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Confirm"
        content="Proceed?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables confirm button when disabled prop is true", () => {
    render(
      <ConfirmDialog
        open
        title="Delete"
        content="Proceed?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        disabled
      />
    );
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });

  it("shows loading state on confirm button", () => {
    render(
      <ConfirmDialog
        open
        title="Confirm"
        content="Proceed?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        loading
      />
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("disables cancel button during loading", () => {
    render(
      <ConfirmDialog
        open
        title="Confirm"
        content="Proceed?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        loading
      />
    );
    expect(screen.getByText("Cancel")).toBeDisabled();
  });

  it("renders with error confirm color", () => {
    render(
      <ConfirmDialog
        open
        title="Danger"
        content="This is dangerous"
        confirmColor="error"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    const btn = screen.getByText("Confirm");
    expect(btn).toBeInTheDocument();
  });

  it("renders without content", () => {
    render(
      <ConfirmDialog
        open
        title="Delete"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
    // No DialogContent should be rendered
    expect(document.querySelector(".MuiDialogContent-root")).not.toBeInTheDocument();
  });

  it("renders ReactNode content", () => {
    render(
      <ConfirmDialog
        open
        title="Confirm"
        content={<span data-testid="custom-content">Custom node</span>}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByTestId("custom-content")).toBeInTheDocument();
  });

  it("has proper aria-labelledby and aria-describedby", () => {
    render(
      <ConfirmDialog
        open
        title="Delete"
        content="Sure?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).toBeInTheDocument();
    expect(dialog?.getAttribute("aria-labelledby")).toBe("confirm-dialog-title");
    expect(dialog?.getAttribute("aria-describedby")).toBe("confirm-dialog-description");
  });
});
