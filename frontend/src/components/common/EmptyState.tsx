import { type ReactNode } from "react";
import { Box, Typography, Button } from "@mui/material";
import InboxIcon from "@mui/icons-material/Inbox";

// ============================================================
// Types
// ============================================================

export interface EmptyStateProps {
  icon?: ReactNode;
  message?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

// ============================================================
// Component
// ============================================================

function EmptyState({
  icon,
  message = "Nothing here",
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      gap={1.5}
      py={4}
      textAlign="center"
    >
      <Box sx={{ color: "text.disabled", mb: 1 }}>
        {icon ?? <InboxIcon sx={{ fontSize: 64 }} />}
      </Box>

      <Typography variant="body1" color="text.secondary">
        {message}
      </Typography>

      {actionLabel && onAction && (
        <Button variant="outlined" size="small" onClick={onAction} sx={{ mt: 1 }}>
          {actionLabel}
        </Button>
      )}
    </Box>
  );
}

export default EmptyState;
