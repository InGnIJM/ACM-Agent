import { Box, CircularProgress, Typography } from "@mui/material";

// ============================================================
// Types
// ============================================================

export interface LoadingSpinnerProps {
  message?: string;
  size?: number;
  fullPage?: boolean;
}

// ============================================================
// Component
// ============================================================

function LoadingSpinner({
  message,
  size = 40,
  fullPage = false,
}: LoadingSpinnerProps) {
  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      gap={2}
      py={fullPage ? 12 : 4}
      sx={fullPage ? { minHeight: "60vh" } : undefined}
      role="status"
      aria-label={message ?? "Loading"}
    >
      <CircularProgress size={size} />
      {message && (
        <Typography variant="body2" color="text.secondary">
          {message}
        </Typography>
      )}
    </Box>
  );
}

export default LoadingSpinner;
