import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    primary: {
      main: "#1E40AF",
      light: "#3B82F6",
      dark: "#1E3A8A",
      contrastText: "#FFFFFF",
    },
    secondary: {
      main: "#3B82F6",
      light: "#60A5FA",
      dark: "#2563EB",
      contrastText: "#FFFFFF",
    },
    background: {
      default: "#F8FAFC",
      paper: "#FFFFFF",
    },
  },
  typography: {
    fontFamily: '"Fira Sans", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 700 },
    h2: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 700 },
    h3: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 600 },
    h4: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 600, fontSize: "2.5rem" },
    h5: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 500, fontSize: "1.75rem" },
    h6: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 500, fontSize: "1.5rem" },
    subtitle1: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 500, fontSize: "1.15rem" },
    subtitle2: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 500, fontSize: "1.05rem" },
    body1: { fontFamily: '"Fira Sans", sans-serif', fontSize: "1.15rem" },
    body2: { fontFamily: '"Fira Sans", sans-serif', fontSize: "1.05rem" },
    button: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 600, textTransform: "none", fontSize: "1.05rem" },
    caption: { fontFamily: '"Fira Sans", sans-serif', fontSize: "0.9rem" },
    overline: { fontFamily: '"Fira Sans", sans-serif', fontWeight: 400, textTransform: "uppercase", letterSpacing: "0.08em" },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        "pre, code, kbd, samp": {
          fontFamily: '"Fira Code", "Consolas", "Monaco", monospace',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
    },
  },
  shape: {
    borderRadius: 8,
  },
});

export default theme;
