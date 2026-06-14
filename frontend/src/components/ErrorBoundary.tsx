import { Component, type ErrorInfo, type ReactNode } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "100vh",
              gap: 2,
              p: 3,
            }}
          >
            <Alert severity="error" sx={{ maxWidth: 500 }}>
              <Typography variant="h6">页面出错了</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                {this.state.error?.message ?? "未知错误"}
              </Typography>
            </Alert>
            <Button variant="contained" onClick={this.handleReset}>
              重试
            </Button>
            <Button variant="outlined" onClick={() => window.location.reload()}>
              刷新页面
            </Button>
          </Box>
        )
      );
    }

    return this.props.children;
  }
}
