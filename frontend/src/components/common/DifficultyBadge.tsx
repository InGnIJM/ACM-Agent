import { Chip, Box, Typography } from "@mui/material";

// ============================================================
// Difficulty → color mapping
// ============================================================

/**
 * 1-3  → success (green / easy)
 * 4-5  → warning (amber / medium)
 * 6-7  → orange  (custom)
 * 8-10 → error   (red / hard)
 */
function getDifficultyColor(difficulty: number): {
  chipColor: "success" | "warning" | "error" | "default";
  hex: string;
} {
  if (difficulty >= 1 && difficulty <= 3) {
    return { chipColor: "success", hex: "#2E7D32" };
  }
  if (difficulty >= 4 && difficulty <= 5) {
    return { chipColor: "warning", hex: "#ED6C02" };
  }
  if (difficulty >= 6 && difficulty <= 7) {
    return { chipColor: "default", hex: "#E65100" };
  }
  return { chipColor: "error", hex: "#C62828" };
}

// ============================================================
// Types
// ============================================================

export type DifficultyVariant = "chip" | "dot" | "text";

export interface DifficultyBadgeProps {
  difficulty: number;
  variant?: DifficultyVariant;
  size?: "small" | "medium";
  showLabel?: boolean;
}

// ============================================================
// Component
// ============================================================

function DifficultyBadge({
  difficulty,
  variant = "chip",
  size = "small",
  showLabel = true,
}: DifficultyBadgeProps) {
  const clamped = Math.max(1, Math.min(10, difficulty));
  const { chipColor, hex } = getDifficultyColor(clamped);

  if (variant === "dot") {
    return (
      <Box display="flex" alignItems="center" gap={1}>
        <Box
          sx={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            backgroundColor: hex,
            display: "inline-block",
            flexShrink: 0,
          }}
          aria-label={`Difficulty ${clamped}`}
        />
        {showLabel && (
          <Typography variant="body2" fontWeight={500}>
            {clamped}
          </Typography>
        )}
      </Box>
    );
  }

  if (variant === "text") {
    return (
      <Typography
        variant={size === "small" ? "body2" : "body1"}
        fontWeight={700}
        color={hex}
        component="span"
      >
        {clamped}
      </Typography>
    );
  }

  // variant === "chip" (default)
  return (
    <Chip
      label={showLabel ? `Lv ${clamped}` : String(clamped)}
      color={chipColor}
      size={size}
      variant="filled"
      sx={{
        fontWeight: 600,
        minWidth: 48,
        ...(chipColor === "default" && {
          backgroundColor: "#E65100",
          color: "#FFFFFF",
        }),
      }}
    />
  );
}

export default DifficultyBadge;
