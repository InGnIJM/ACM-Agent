import { Chip, type ChipProps } from "@mui/material";

// ============================================================
// Status → display config
// ============================================================

interface VerdictConfig {
  label: string;
  color: ChipProps["color"];
  hex: string;
}

const VERDICT_MAP: Record<string, VerdictConfig> = {
  accepted: { label: "Accepted", color: "success", hex: "#2E7D32" },
  ok: { label: "OK", color: "success", hex: "#2E7D32" },
  wrong_answer: { label: "Wrong Answer", color: "error", hex: "#C62828" },
  wa: { label: "WA", color: "error", hex: "#C62828" },
  time_limit: { label: "Time Limit", color: "warning", hex: "#ED6C02" },
  tle: { label: "TLE", color: "warning", hex: "#ED6C02" },
  memory_limit: { label: "Memory Limit", color: "warning", hex: "#E65100" },
  mle: { label: "MLE", color: "warning", hex: "#E65100" },
  runtime_error: { label: "Runtime Error", color: "error", hex: "#C62828" },
  re: { label: "RE", color: "error", hex: "#C62828" },
  compilation_error: { label: "Compile Error", color: "error", hex: "#7B1FA2" },
  ce: { label: "CE", color: "error", hex: "#7B1FA2" },
  pending: { label: "Pending", color: "default", hex: "#757575" },
};

// ============================================================
// Types
// ============================================================

export interface VerdictBadgeProps {
  status: string;
  size?: "small" | "medium";
  variant?: "filled" | "outlined";
}

// ============================================================
// Component
// ============================================================

function VerdictBadge({
  status,
  size = "small",
  variant = "filled",
}: VerdictBadgeProps) {
  const key = status.toLowerCase().trim();
  const config = VERDICT_MAP[key] ?? {
    label: status,
    color: "default" as ChipProps["color"],
    hex: "#9E9E9E",
  };

  return (
    <Chip
      label={config.label}
      color={config.color}
      size={size}
      variant={variant}
      sx={{
        fontWeight: 600,
        minWidth: 64,
        ...(config.color === "default" && {
          backgroundColor: config.hex,
          color: "#FFFFFF",
        }),
      }}
    />
  );
}

export default VerdictBadge;
