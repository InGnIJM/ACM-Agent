import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import useAuth from "../hooks/useAuth";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, Radar,
} from "recharts";

export default function Dashboard() {
  const { user, loading: authLoading } = useAuth();

  if (authLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "60vh" }}>
        <Skeleton variant="circular" width={60} height={60} />
      </Box>
    );
  }

  if (!user) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">请先登录</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        控制台
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        欢迎回来，{user.nickname ?? user.username}
      </Typography>

      {/* ---- stats cards ---- */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={6} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">用户名</Typography>
            <Typography variant="h5" color="primary.main">{user.username}</Typography>
          </Paper>
        </Grid>
        <Grid item xs={6} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">角色</Typography>
            <Typography variant="h5" color="secondary.main">{user.role}</Typography>
          </Paper>
        </Grid>
        <Grid item xs={6} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">学号</Typography>
            <Typography variant="h5">{user.studentId ?? "-"}</Typography>
          </Paper>
        </Grid>
        <Grid item xs={6} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">注册时间</Typography>
            <Typography variant="body1">{new Date(user.createdAt).toLocaleDateString("zh-CN")}</Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* ---- charts row (placeholder data) ---- */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>每日训练趋势（示例）</Typography>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={[
                { day: "周一", ac: 3 }, { day: "周二", ac: 5 }, { day: "周三", ac: 2 },
                { day: "周四", ac: 7 }, { day: "周五", ac: 4 }, { day: "周六", ac: 6 }, { day: "周日", ac: 8 },
              ]}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Line type="monotone" dataKey="ac" stroke="#1E40AF" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>难度分布（示例）</Typography>
            <ResponsiveContainer width="100%" height={280}>
              <RadarChart data={[
                { name: "简单", value: 30, fill: "#22C55E" },
                { name: "中等", value: 15, fill: "#F59E0B" },
                { name: "困难", value: 5, fill: "#EF4444" },
              ]}>
                <PolarGrid />
                <PolarAngleAxis dataKey="name" />
                <PolarRadiusAxis angle={30} domain={[0, "auto"]} />
                <Radar name="通过数" dataKey="value" stroke="#1E40AF" fill="#1E40AF" fillOpacity={0.3} />
              </RadarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
      </Grid>

      {/* ---- difficulty chips ---- */}
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>难度分布</Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <Chip label="简单: 30" sx={{ bgcolor: "#22C55E", color: "#fff", fontWeight: 600 }} />
          <Chip label="中等: 15" sx={{ bgcolor: "#F59E0B", color: "#fff", fontWeight: 600 }} />
          <Chip label="困难: 5" sx={{ bgcolor: "#EF4444", color: "#fff", fontWeight: 600 }} />
        </Box>
      </Paper>
    </Box>
  );
}
