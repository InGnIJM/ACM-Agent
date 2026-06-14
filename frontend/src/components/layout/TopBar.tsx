// ============================================================
// TopBar — AppBar with user menu and team name (desktop)
// ============================================================

import { useState, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Avatar from "@mui/material/Avatar";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Divider from "@mui/material/Divider";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import GroupsIcon from "@mui/icons-material/Groups";
import PersonIcon from "@mui/icons-material/Person";
import SettingsIcon from "@mui/icons-material/Settings";
import LogoutIcon from "@mui/icons-material/Logout";
import useAuth from "../../hooks/useAuth";
function isAdmin(role?: string): boolean { return role === "admin"; }

// ---- helpers ----

function avatarLetter(name: string): string {
  return (name || "?").charAt(0).toUpperCase();
}

function displayName(username: string, nickname?: string): string {
  return nickname || username;
}

// ---- component ----

export default function TopBar() {
  const { user, team, logout } = useAuth();
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const menuOpen = Boolean(anchorEl);

  function openMenu(e: MouseEvent<HTMLElement>) {
    setAnchorEl(e.currentTarget);
  }

  function closeMenu() {
    setAnchorEl(null);
  }

  function handleProfile() {
    closeMenu();
    navigate("/profile");
  }

  function handleSettings() {
    closeMenu();
    navigate("/settings");
  }

  function handleLogout() {
    closeMenu();
    logout();
    navigate("/login");
  }

  if (!user) return null;

  const name = displayName(user.username, user.nickname);

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        backgroundColor: "background.paper",
        borderBottom: "1px solid",
        borderColor: "divider",
        color: "text.primary",
        zIndex: (t) => t.zIndex.drawer + 1,
      }}
    >
      <Toolbar sx={{ justifyContent: "space-between", minHeight: "64px !important" }}>
        {/* Left — team name */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {team ? (
            <Chip
              icon={<GroupsIcon />}
              label={team.name}
              size="small"
              variant="outlined"
              color="primary"
              sx={{ fontWeight: 500 }}
            />
          ) : (
            <Typography variant="body2" color="text.secondary">
              No team selected
            </Typography>
          )}
        </Box>

        {/* Right — user */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Typography
            variant="body2"
            sx={{ fontWeight: 500, display: { xs: "none", sm: "block" } }}
          >
            {name}
          </Typography>

          <Tooltip title="Account menu">
            <IconButton
              onClick={openMenu}
              size="small"
              aria-controls={menuOpen ? "account-menu" : undefined}
              aria-haspopup="true"
              aria-expanded={menuOpen ? "true" : undefined}
            >
              <Avatar
                src={user.avatar_url}
                alt={name}
                sx={{
                  width: 34,
                  height: 34,
                  bgcolor: "primary.main",
                  fontSize: 16,
                  fontWeight: 600,
                }}
              >
                {!user.avatar_url && avatarLetter(name)}
              </Avatar>
            </IconButton>
          </Tooltip>

          <Menu
            id="account-menu"
            anchorEl={anchorEl}
            open={menuOpen}
            onClose={closeMenu}
            onClick={closeMenu}
            transformOrigin={{ horizontal: "right", vertical: "top" }}
            anchorOrigin={{ horizontal: "right", vertical: "bottom" }}
            slotProps={{
              paper: {
                elevation: 3,
                sx: {
                  minWidth: 200,
                  mt: 1,
                  borderRadius: 2,
                  overflow: "visible",
                  "&::before": {
                    content: '""',
                    display: "block",
                    position: "absolute",
                    top: 0,
                    right: 14,
                    width: 10,
                    height: 10,
                    bgcolor: "background.paper",
                    transform: "translateY(-50%) rotate(45deg)",
                    zIndex: 0,
                  },
                },
              },
            }}
          >
            {/* User info header */}
            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography variant="subtitle2" fontWeight={600} noWrap>
                {name}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {user.email}
              </Typography>
            </Box>

            <Divider />

            <MenuItem onClick={handleProfile}>
              <ListItemIcon>
                <PersonIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>Profile</ListItemText>
            </MenuItem>

            <MenuItem onClick={handleSettings}>
              <ListItemIcon>
                <SettingsIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>Settings</ListItemText>
            </MenuItem>

            <Divider />

            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <LogoutIcon fontSize="small" color="error" />
              </ListItemIcon>
              <ListItemText primary="Logout" primaryTypographyProps={{ color: "error" }} />
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
}
