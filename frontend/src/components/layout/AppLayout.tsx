import { useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMediaQuery, useTheme } from "@mui/material";
import Box from "@mui/material/Box";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import Paper from "@mui/material/Paper";
import CircularProgress from "@mui/material/CircularProgress";
import DashboardIcon from "@mui/icons-material/Dashboard";
import CodeIcon from "@mui/icons-material/Code";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";
import PersonIcon from "@mui/icons-material/Person";
import SettingsIcon from "@mui/icons-material/Settings";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import useAuth from "../../hooks/useAuth";

const BOTTOM_NAV_ITEMS = [
  { label: "控制台", path: "/", icon: <DashboardIcon /> },
  { label: "题库", path: "/problems", icon: <CodeIcon /> },
  { label: "记录", path: "/records", icon: <ReceiptLongIcon /> },
  { label: "画像", path: "/profile", icon: <PersonIcon /> },
  { label: "设置", path: "/settings", icon: <SettingsIcon /> },
];

const BOTTOM_NAV_HEIGHT = 56;

interface AppLayoutProps {
  children: ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const { loading } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  // Mobile
  if (isMobile) {
    const currentPath = location.pathname;
    return (
      <Box sx={{ display: "flex", flexDirection: "column", minHeight: "100vh", backgroundColor: "background.default" }}>
        <Box component="main" sx={{ flex: 1, pb: `${BOTTOM_NAV_HEIGHT + 8}px`, overflow: "auto" }}>
          {children}
        </Box>
        <Paper sx={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: (t) => t.zIndex.appBar, borderTop: "1px solid", borderColor: "divider" }} elevation={3}>
          <BottomNavigation
            value={BOTTOM_NAV_ITEMS.findIndex((item) => (item.path === "/" ? currentPath === "/" : currentPath.startsWith(item.path)))}
            onChange={(_e, idx) => { if (idx >= 0 && idx < BOTTOM_NAV_ITEMS.length) navigate(BOTTOM_NAV_ITEMS[idx].path); }}
            sx={{ height: BOTTOM_NAV_HEIGHT }}
          >
            {BOTTOM_NAV_ITEMS.map((item) => (
              <BottomNavigationAction key={item.path} label={item.label} icon={item.icon} showLabel sx={{ minWidth: 0, px: 0.5, "&.Mui-selected": { color: "primary.main" } }} />
            ))}
          </BottomNavigation>
        </Paper>
      </Box>
    );
  }

  // Desktop
  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />
      <Box sx={{ display: "flex", flexDirection: "column", flex: 1, transition: (t) => t.transitions.create("margin-left", { easing: t.transitions.easing.sharp, duration: t.transitions.duration.enteringScreen }) }}>
        <TopBar />
        <Box component="main" sx={{ flex: 1, p: 2, backgroundColor: "background.default", overflow: "auto" }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}
