// ============================================================
// AdminGuard — renders children only if the current user has
// the "admin" role; otherwise redirects to /.
// ============================================================

import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import useAuth from "../hooks/useAuth";

interface Props {
  children: ReactNode;
}

export default function AdminGuard({ children }: Props) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (!user || user.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
