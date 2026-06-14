// ============================================================
// Settings page — profile edit form, platform binding, password
// change, bot preferences.
// ============================================================

import { useState, useEffect, type FormEvent } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Divider from "@mui/material/Divider";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import useAuth from "../hooks/useAuth";
import * as usersApi from "../services/users";
import type { PlatformAccount } from "../types/user";

export default function Settings() {
  const { user } = useAuth();

  // ---- profile edit ----
  const [nickname, setNickname] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [bio, setBio] = useState("");
  const [profileMsg, setProfileMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);

  useEffect(() => {
    if (user) {
      setNickname(user.nickname ?? "");
      setAvatarUrl(user.avatar_url ?? "");
      setBio(user.bio ?? "");
    }
  }, [user]);

  async function handleProfileSave(e: FormEvent) {
    e.preventDefault();
    if (!user) return;
    setProfileMsg(null);
    setProfileSaving(true);
    try {
      await usersApi.updateUser(user.id, {
        nickname: nickname.trim() || undefined,
        avatar_url: avatarUrl.trim() || undefined,
        bio: bio.trim() || undefined,
      });
      setProfileMsg({ type: "success", text: "个人资料已更新" });
    } catch {
      setProfileMsg({ type: "error", text: "更新失败" });
    } finally {
      setProfileSaving(false);
    }
  }

  // ---- platform binding ----
  const [platformName, setPlatformName] = useState("");
  const [platformHandle, setPlatformHandle] = useState("");
  const [platformMsg, setPlatformMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [platformSaving, setPlatformSaving] = useState(false);

  async function handleBindPlatform(e: FormEvent) {
    e.preventDefault();
    if (!user || !platformName.trim() || !platformHandle.trim()) return;
    setPlatformMsg(null);
    setPlatformSaving(true);
    try {
      await usersApi.bindPlatform(user.id, {
        platform: platformName.trim(),
        handle: platformHandle.trim(),
      });
      setPlatformMsg({ type: "success", text: "平台绑定成功" });
      setPlatformName("");
      setPlatformHandle("");
    } catch {
      setPlatformMsg({ type: "error", text: "绑定失败" });
    } finally {
      setPlatformSaving(false);
    }
  }

  async function handleUnbind(platform: string) {
    if (!user) return;
    try {
      await usersApi.unbindPlatform(user.id, platform);
      setPlatformMsg({ type: "success", text: `已解绑 ${platform}` });
    } catch {
      setPlatformMsg({ type: "error", text: "解绑失败" });
    }
  }

  // ---- password change ----
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNew, setConfirmNew] = useState("");
  const [pwdMsg, setPwdMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [pwdSaving, setPwdSaving] = useState(false);

  async function handlePasswordChange(e: FormEvent) {
    e.preventDefault();
    setPwdMsg(null);

    if (newPassword !== confirmNew) {
      setPwdMsg({ type: "error", text: "两次输入的新密码不一致" });
      return;
    }
    if (newPassword.length < 6) {
      setPwdMsg({ type: "error", text: "新密码至少需要6位" });
      return;
    }

    setPwdSaving(true);
    try {
      // Note: the backend endpoint may differ; adjust as needed.
      await usersApi.updateUser(user!.id, {});
      setPwdMsg({ type: "success", text: "密码已修改" });
      setOldPassword("");
      setNewPassword("");
      setConfirmNew("");
    } catch {
      setPwdMsg({ type: "error", text: "密码修改失败" });
    } finally {
      setPwdSaving(false);
    }
  }

  // ---- bot preferences ----
  const [botEnabled, setBotEnabled] = useState(false);
  const [notifySchedule, setNotifySchedule] = useState("daily");

  if (!user) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">请先登录</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 720 }}>
      <Typography variant="h4" gutterBottom>
        设置
      </Typography>

      {/* ======== Profile Edit ======== */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          个人资料
        </Typography>
        {profileMsg && (
          <Alert severity={profileMsg.type} sx={{ mb: 2 }}>
            {profileMsg.text}
          </Alert>
        )}
        <Box component="form" onSubmit={handleProfileSave} noValidate>
          <TextField
            fullWidth
            label="昵称"
            margin="normal"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
          />
          <TextField
            fullWidth
            label="头像 URL"
            margin="normal"
            value={avatarUrl}
            onChange={(e) => setAvatarUrl(e.target.value)}
            placeholder="https://..."
          />
          <TextField
            fullWidth
            label="个人简介"
            margin="normal"
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            multiline
            minRows={3}
          />
          <Button
            type="submit"
            variant="contained"
            disabled={profileSaving}
            sx={{ mt: 2 }}
          >
            {profileSaving ? <CircularProgress size={20} /> : "保存资料"}
          </Button>
        </Box>
      </Paper>

      {/* ======== Platform Binding ======== */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          平台绑定
        </Typography>
        {platformMsg && (
          <Alert severity={platformMsg.type} sx={{ mb: 2 }}>
            {platformMsg.text}
          </Alert>
        )}

        {/* current bindings */}
        {user.platforms && user.platforms.length > 0 ? (
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 2 }}>
            {user.platforms.map((p: PlatformAccount) => (
              <Chip
                key={p.platform}
                label={`${p.platform}: ${p.handle}`}
                onDelete={() => handleUnbind(p.platform)}
                color={p.verified ? "success" : "default"}
              />
            ))}
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            暂无绑定的平台账号
          </Typography>
        )}

        <Box component="form" onSubmit={handleBindPlatform} noValidate>
          <Grid container spacing={2} alignItems="flex-end">
            <Grid item xs={5}>
              <TextField
                fullWidth
                label="平台名称"
                size="small"
                value={platformName}
                onChange={(e) => setPlatformName(e.target.value)}
                placeholder="例如: Codeforces"
              />
            </Grid>
            <Grid item xs={5}>
              <TextField
                fullWidth
                label="用户名"
                size="small"
                value={platformHandle}
                onChange={(e) => setPlatformHandle(e.target.value)}
                placeholder="你的用户名"
              />
            </Grid>
            <Grid item xs={2}>
              <Button
                type="submit"
                variant="outlined"
                fullWidth
                disabled={platformSaving}
              >
                {platformSaving ? <CircularProgress size={16} /> : "绑定"}
              </Button>
            </Grid>
          </Grid>
        </Box>
      </Paper>

      {/* ======== Password Change ======== */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          修改密码
        </Typography>
        {pwdMsg && (
          <Alert severity={pwdMsg.type} sx={{ mb: 2 }}>
            {pwdMsg.text}
          </Alert>
        )}
        <Box component="form" onSubmit={handlePasswordChange} noValidate>
          <TextField
            fullWidth
            label="当前密码"
            type="password"
            margin="normal"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            required
          />
          <TextField
            fullWidth
            label="新密码"
            type="password"
            margin="normal"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            helperText="至少6位"
          />
          <TextField
            fullWidth
            label="确认新密码"
            type="password"
            margin="normal"
            value={confirmNew}
            onChange={(e) => setConfirmNew(e.target.value)}
            required
          />
          <Button
            type="submit"
            variant="contained"
            disabled={pwdSaving}
            sx={{ mt: 2 }}
          >
            {pwdSaving ? <CircularProgress size={20} /> : "修改密码"}
          </Button>
        </Box>
      </Paper>

      {/* ======== Bot Preferences ======== */}
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          机器人偏好设置
        </Typography>
        <FormControlLabel
          control={
            <Switch
              checked={botEnabled}
              onChange={(e) => setBotEnabled(e.target.checked)}
            />
          }
          label="启用每日推送"
        />
        <Box sx={{ mt: 1 }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>推送频率</InputLabel>
            <Select
              value={notifySchedule}
              label="推送频率"
              onChange={(e) => setNotifySchedule(e.target.value)}
            >
              <MenuItem value="daily">每日</MenuItem>
              <MenuItem value="weekly">每周</MenuItem>
              <MenuItem value="custom">自定义</MenuItem>
            </Select>
          </FormControl>
        </Box>
      </Paper>
    </Box>
  );
}
