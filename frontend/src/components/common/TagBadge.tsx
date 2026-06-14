import { Chip, type ChipProps } from "@mui/material";

// ============================================================
// Tag category → MUI color mapping
// ============================================================

const TAG_COLOR_MAP: Record<string, ChipProps["color"]> = {
  data_structure: "primary",
  search: "success",
  dp: "warning",
  graph: "error",
  math: "info",
  string: "secondary",
  greedy: "default",
};

export type TagCategory = keyof typeof TAG_COLOR_MAP;

// ============================================================
// Types
// ============================================================

export interface TagBadgeProps {
  label: string;
  category?: TagCategory | string;
  size?: "small" | "medium";
  variant?: "filled" | "outlined";
  onClick?: () => void;
  onDelete?: () => void;
}

// ============================================================
// Component
// ============================================================

function TagBadge({
  label,
  category,
  size = "small",
  variant = "filled",
  onClick,
  onDelete,
}: TagBadgeProps) {
  const color: ChipProps["color"] = category
    ? (TAG_COLOR_MAP[category] ?? "default")
    : "default";

  return (
    <Chip
      label={label}
      color={color}
      size={size}
      variant={variant}
      onClick={onClick}
      onDelete={onDelete}
      clickable={!!onClick}
      sx={{
        fontWeight: 500,
        m: 0.25,
      }}
    />
  );
}

export default TagBadge;
