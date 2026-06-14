import { useMemo, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import Toolbar from "@mui/material/Toolbar";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import DashboardIcon from "@mui/icons-material/Dashboard";
import CodeIcon from "@mui/icons-material/Code";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";
import PersonIcon from "@mui/icons-material/Person";
import SchoolIcon from "@mui/icons-material/School";
import GroupWorkIcon from "@mui/icons-material/GroupWork";
import GroupsIcon from "@mui/icons-material/Groups";
import EmojiEventsIcon from "@mui/icons-material/EmojiEvents";
import SettingsIcon from "@mui/icons-material/Settings";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import MenuIcon from "@mui/icons-material/Menu";
import useAuth from "../../hooks/useAuth";

function isAdminRole(role?: string): boolean { return role === "admin"; }

interface NavItem {
  label: string;
  path: string;
  icon: ReactNode;
}

export const DRAWER_WIDTH = 220;
export const DRAWER_COLLAPSED = 64;

const USER_ITEMS: NavItem[] = [
  { label: "控制台", path: "/", icon: <DashboardIcon /> },
  { label: "题库", path: "/problems", icon: <CodeIcon /> },
  { label: "练习记录", path: "/records", icon: <ReceiptLongIcon /> },
  { label: "用户画像", path: "/profile", icon: <PersonIcon /> },
  { label: "训练计划", path: "/training", icon: <SchoolIcon /> },
  { label: "队友匹配", path: "/matching", icon: <GroupWorkIcon /> },
  { label: "队伍管理", path: "/teams", icon: <GroupsIcon /> },
  { label: "排行榜", path: "/ranking", icon: <EmojiEventsIcon /> },
  { label: "设置", path: "/settings", icon: <SettingsIcon /> },
];

const ADMIN_ITEMS: NavItem[] = [
  { label: "用户管理", path: "/admin/users", icon: <AdminPanelSettingsIcon /> },
  { label: "爬虫管理", path: "/admin/crawler", icon: <TravelExploreIcon /> },
  { label: "Bot 配置", path: "/admin/bot", icon: <SmartToyIcon /> },
];

interface SidebarProps {
  open: boolean;
  onToggle: () => void;
}

export default function Sidebar({ open, onToggle }: SidebarProps) {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const admin = isAdminRole(user?.role);
  const expanded = open;

  const items = useMemo<NavItem[]>(() => {
    return admin ? [...USER_ITEMS, ...ADMIN_ITEMS] : USER_ITEMS;
  }, [admin]);

  function isActive(path: string): boolean {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  }

  function handleNav(path: string) {
    navigate(path);
  }

  const drawerWidth = expanded ? DRAWER_WIDTH : DRAWER_COLLAPSED;

  return (
    <Drawer
      variant="permanent"
      anchor="left"
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        whiteSpace: "nowrap",
        transition: (t) => t.transitions.create("width", {
          easing: t.transitions.easing.sharp,
          duration: t.transitions.duration.enteringScreen,
        }),
        "& .MuiDrawer-paper": {
          width: drawerWidth,
          boxSizing: "border-box",
          borderRight: "1px solid",
          borderColor: "divider",
          overflowX: "hidden",
          transition: (t) => t.transitions.create("width", {
            easing: t.transitions.easing.sharp,
            duration: t.transitions.duration.enteringScreen,
          }),
        },
      }}
    >
      <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <Toolbar sx={{ px: expanded ? 2 : 1, gap: 1, minHeight: "64px !important", justifyContent: expanded ? "flex-start" : "center" }}>
          {expanded ? (
            <>
              <Box sx={{ width: 32, height: 32, borderRadius: 1.5, background: (t) => `linear-gradient(135deg, ${t.palette.primary.main}, ${t.palette.primary.light})`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontSize: 16, flexShrink: 0 }}>
                A
              </Box>
              <Typography variant="h6" noWrap sx={{ fontWeight: 700, color: "primary.main", fontSize: 18 }}>
                ACM Agent
              </Typography>
            </>
          ) : (
            <Box sx={{ width: 32, height: 32, borderRadius: 1.5, background: (t) => `linear-gradient(135deg, ${t.palette.primary.main}, ${t.palette.primary.light})`, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontSize: 16 }}>
              A
            </Box>
          )}
        </Toolbar>

        <Divider />

        {/* Toggle button */}
        <Box sx={{ display: "flex", justifyContent: expanded ? "flex-end" : "center", p: 0.5 }}>
          <IconButton onClick={onToggle} size="small">
            {expanded ? <ChevronLeftIcon /> : <MenuIcon />}
          </IconButton>
        </Box>

        <Divider />

        {/* Nav items */}
        <Box sx={{ flex: 1, overflow: "auto", py: 0.5 }}>
          <List dense disablePadding>
            {items.map((item) => {
              const active = isActive(item.path);
              const btn = (
                <ListItemButton
                  key={item.path}
                  onClick={() => handleNav(item.path)}
                  selected={active}
                  sx={{
                    mx: 0.5,
                    my: 0.25,
                    borderRadius: 1.5,
                    minHeight: 40,
                    justifyContent: expanded ? "initial" : "center",
                    px: expanded ? 1.5 : 1,
                    "&.Mui-selected": {
                      backgroundColor: "primary.main",
                      color: "primary.contrastText",
                      "&:hover": { backgroundColor: "primary.dark" },
                      "& .MuiListItemIcon-root": { color: "primary.contrastText" },
                    },
                    "&:hover": { backgroundColor: "action.hover" },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: expanded ? 36 : 0, mr: expanded ? 1 : 0, justifyContent: "center", color: active ? "inherit" : "text.secondary" }}>
                    {item.icon}
                  </ListItemIcon>
                  {expanded && (
                    <ListItemText
                      primary={item.label}
                      primaryTypographyProps={{ variant: "body2", fontWeight: active ? 600 : 400, noWrap: true }}
                    />
                  )}
                </ListItemButton>
              );

              return expanded ? btn : (
                <Tooltip key={item.path} title={item.label} placement="right" arrow>
                  {btn}
                </Tooltip>
              );
            })}
          </List>
        </Box>

        {/* Footer */}
        {expanded && (
          <>
            <Divider />
            <Box sx={{ p: 1.5 }}>
              <Typography variant="caption" color="text.secondary">ACM Agent v1.0.0</Typography>
            </Box>
          </>
        )}
      </Box>
    </Drawer>
  );
}
