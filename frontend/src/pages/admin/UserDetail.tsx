import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Divider from "@mui/material/Divider";
import Alert from "@mui/material/Alert";
import Skeleton from "@mui/material/Skeleton";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import useApi from "../../hooks/useApi";
import * as usersApi from "../../services/users";

interface ApiUser {
  id: string; username: string; role: string; nickname?: string;
  email?: string; realName?: string; studentId?: string;
  department?: string; major?: string; grade?: string;
  createdAt: string; updatedAt: string;
}

export default function UserDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const fetcher = useCallback(() => usersApi.getUser(id!), [id]);
  const { data: user, loading, error } = useApi<ApiUser>(fetcher, [id]);

  const [nickname, setNickname] = useState("");
  const [email, setEmail] = useState("");
  const [realName, setRealName] = useState("");
  const [studentId, setStudentId] = useState("");
  const [department, setDepartment] = useState("");
  const [major, setMajor] = useState("");
  const [grade, setGrade] = useState("");
  const [role, setRole] = useState("user");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (user) {
      setNickname(user.nickname ?? "");
      setEmail(user.email ?? "");
      setRealName((user as any).realName ?? "");
      setStudentId((user as any).studentId ?? "");
      setDepartment((user as any).department ?? "");
      setMajor((user as any).major ?? "");
      setGrade((user as any).grade ?? "");
      setRole(user.role ?? "user");
    }
  }, [user]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      await usersApi.updateUser(id!, {
        nickname, email, realName, studentId, department, major, grade,
      } as any);
      setMsg({ type: "success", text: "保存成功" });
    } catch (err: any) {
      setMsg({ type: "error", text: err.message ?? "保存失败" });
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Box sx={{ p: 3 }}><Skeleton variant="text" width={300} height={40} /><Skeleton variant="rectangular" height={200} sx={{ mt: 2 }} /></Box>;
  if (error || !user) return <Box sx={{ p: 3 }}><Alert severity="error">{String(error ?? "用户未找到")}</Alert></Box>;

  return (
    <Box sx={{ p: 3 }}>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/admin/users")} sx={{ mb: 2 }}>返回用户列表</Button>

      <Typography variant="h4" gutterBottom>编辑用户</Typography>

      {msg && <Alert severity={msg.type} sx={{ mb: 2 }}>{msg.text}</Alert>}

      <Paper sx={{ p: 3 }}>
        <Box component="form" onSubmit={handleSave}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="用户名" value={user.username} disabled size="small" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth size="small">
                <InputLabel>角色</InputLabel>
                <Select value={role} label="角色" onChange={e => setRole(e.target.value)}>
                  <MenuItem value="user">普通用户</MenuItem>
                  <MenuItem value="observed">观测用户</MenuItem>
                  <MenuItem value="admin">管理员</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="昵称" value={nickname} onChange={e => setNickname(e.target.value)} size="small" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="邮箱" value={email} onChange={e => setEmail(e.target.value)} size="small" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="真实姓名" value={realName} onChange={e => setRealName(e.target.value)} size="small" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="学号" value={studentId} onChange={e => setStudentId(e.target.value)} size="small" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="院系" value={department} onChange={e => setDepartment(e.target.value)} size="small" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="专业" value={major} onChange={e => setMajor(e.target.value)} size="small" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth label="年级" value={grade} onChange={e => setGrade(e.target.value)} size="small" />
            </Grid>
          </Grid>

          <Box sx={{ mt: 3, display: "flex", gap: 2 }}>
            <Button type="submit" variant="contained" disabled={saving}>
              {saving ? <CircularProgress size={20} /> : "保存"}
            </Button>
            <Button variant="outlined" onClick={() => navigate("/admin/users")}>取消</Button>
          </Box>
        </Box>
      </Paper>

      <Divider sx={{ my: 3 }} />

      <Typography variant="subtitle1" gutterBottom>用户信息</Typography>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Chip label={`ID: ${user.id}`} size="small" variant="outlined" />
        <Chip label={`用户名: ${user.username}`} size="small" variant="outlined" />
        <Chip label={`注册时间: ${new Date(user.createdAt).toLocaleDateString("zh-CN")}`} size="small" variant="outlined" />
      </Box>
    </Box>
  );
}
