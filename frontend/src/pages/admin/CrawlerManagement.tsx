import { useState, useEffect, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Chip from "@mui/material/Chip";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Grid from "@mui/material/Grid";
import Alert from "@mui/material/Alert";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import IconButton from "@mui/material/IconButton";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import InfoIcon from "@mui/icons-material/Info";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import LoginIcon from "@mui/icons-material/Login";
import DeleteIcon from "@mui/icons-material/Delete";
import api from "../../services/api";

type LogEntry = { time: string; message: string; level: "info" | "error" | "success" };

const PLATFORMS = ["luogu", "leetcode", "codeforces", "nowcoder", "atcoder"] as const;
const ACTIONS = [
  { value: "fetch_problems", label: "爬取题目", needsTag: true, needsCount: true },
  { value: "fetch_solutions", label: "爬取题解", needsUid: true },
  { value: "fetch_user", label: "爬取用户信息", needsUid: true },
  { value: "fetch_records", label: "爬取用户记录", needsUid: true },
  { value: "import", label: "导入数据到数据库", needsCount: false },
];

export default function CrawlerManagement() {
  const [platform, setPlatform] = useState<string>("luogu");
  const [action, setAction] = useState("fetch_problems");
  const [uid, setUid] = useState("");
  const [tag, setTag] = useState("");
  const [count, setCount] = useState(10);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [running, setRunning] = useState(false);
  const [cookieStatus, setCookieStatus] = useState<Record<string, boolean>>({});

  const checkCookies = useCallback(async () => {
    const result: Record<string, boolean> = {};
    for (const p of PLATFORMS) {
      try {
        const resp = await api.get(`/crawler/cookies/${p}`);
        result[p] = (resp.data as any).hasCookies === true;
      } catch { result[p] = false; }
    }
    setCookieStatus(result);
  }, []);

  useEffect(() => { checkCookies(); }, [checkCookies]);

  function addLog(message: string, level: LogEntry["level"] = "info") {
    setLogs(prev => [...prev.slice(-199), { time: new Date().toLocaleTimeString(), message, level }]);
  }

  async function handleLogin(p: string) {
    addLog(`正在打开 ${p} 浏览器登录页面...`);
    try {
      await api.post(`/crawler/login/${p}`);
      addLog(`${p} 登录页面已打开，请在浏览器中完成登录`, "success");
      // Poll for cookie status update (every 3s, up to 20 times)
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 3000));
        try {
          const resp = await api.get(`/crawler/cookies/${p}`);
          if ((resp.data as any).hasCookies) {
            addLog(`${p} 登录成功！`, "success");
            await checkCookies();
            return;
          }
        } catch {}
        addLog(`${p} 等待登录中... (${i + 1}/20)`);
      }
      addLog(`${p} 登录超时，请重试`, "error");
      await checkCookies();
    } catch (e: any) {
      addLog(`${p} 登录失败: ${e.message ?? String(e)}`, "error");
    }
  }

  async function doRun() {
    setRunning(true);
    const act = ACTIONS.find(a => a.value === action);
    addLog(`[${platform}] 开始: ${act?.label ?? action}`);

    try {
      const resp = await api.post("/crawler/trigger/problems", {
        platform, action, uid: uid || undefined, tags: tag || undefined, count,
      });
      addLog(`[${platform}] 成功: ${JSON.stringify(resp.data)}`, "success");
    } catch (e: any) {
      addLog(`[${platform}] 错误: ${e.message ?? String(e)}`, "error");
    }
    setRunning(false);
  }

  function clearLogs() { setLogs([]); }

  const currentAction = ACTIONS.find(a => a.value === action);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>爬虫管理</Typography>

      <Alert severity="info" sx={{ mb: 2 }}>
        点击登录按钮后会在服务器端打开浏览器窗口，在弹出的浏览器中完成手动登录，Cookie 会自动保存到 <code>data/cookies/</code> 目录，后续爬虫自动复用。
      </Alert>

      {/* Cookie 状态 */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="subtitle1" gutterBottom>平台登录</Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {PLATFORMS.map(p => {
            const loggedIn = cookieStatus[p] === true;
            return loggedIn ? (
              <Chip key={p} icon={<CheckCircleIcon />} label={`${p} 已登录`} color="success" variant="filled" />
            ) : (
              <Button key={p} variant="outlined" size="small" startIcon={<LoginIcon />} onClick={() => handleLogin(p)}>
                登录 {p}
              </Button>
            );
          })}
        </Box>
      </Paper>

      {/* 控制面板 */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>爬取任务</Typography>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={6} sm={2}>
            <FormControl fullWidth size="small">
              <InputLabel>平台</InputLabel>
              <Select value={platform} label="平台" onChange={e => setPlatform(e.target.value)}>
                {PLATFORMS.map(p => <MenuItem key={p} value={p}>{p}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={6} sm={3}>
            <FormControl fullWidth size="small">
              <InputLabel>操作</InputLabel>
              <Select value={action} label="操作" onChange={e => setAction(e.target.value)}>
                {ACTIONS.map(a => <MenuItem key={a.value} value={a.value}>{a.label}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>

          {currentAction?.needsUid && (
            <Grid item xs={6} sm={2}>
              <TextField fullWidth size="small" label="ID" value={uid} onChange={e => setUid(e.target.value)} placeholder="P1001" />
            </Grid>
          )}

          {currentAction?.needsTag && (
            <Grid item xs={6} sm={2}>
              <TextField fullWidth size="small" label="标签" value={tag} onChange={e => setTag(e.target.value)} placeholder="P / DP" />
            </Grid>
          )}

          {(currentAction?.needsCount ?? true) && (
            <Grid item xs={4} sm={1}>
              <TextField fullWidth size="small" label="数量" type="number" value={count} onChange={e => setCount(Number(e.target.value))} inputProps={{ min: 1, max: 1000 }} />
            </Grid>
          )}

          <Grid item xs={8} sm={2}>
            <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={doRun} disabled={running} fullWidth>
              {running ? "运行中..." : "执行"}
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {/* 日志面板 */}
      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
          <Typography variant="h6">运行日志</Typography>
          <IconButton size="small" onClick={clearLogs}><DeleteIcon fontSize="small" /></IconButton>
        </Box>
        {logs.length === 0 ? (
          <Typography color="text.secondary" variant="body2">暂无日志</Typography>
        ) : (
          <List dense disablePadding sx={{ maxHeight: 500, overflow: "auto", bgcolor: "#1e1e2e", borderRadius: 1, p: 1 }}>
            {logs.map((l, i) => (
              <ListItem key={i} sx={{ py: 0.25, color: "#cdd6f4" }}>
                <IconButton size="small" sx={{ color: l.level === "error" ? "#ef4444" : l.level === "success" ? "#22c55e" : "#6b7280", mr: 0.5 }}>
                  {l.level === "error" ? <ErrorIcon fontSize="inherit" /> : l.level === "success" ? <CheckCircleIcon fontSize="inherit" /> : <InfoIcon fontSize="inherit" />}
                </IconButton>
                <ListItemText primary={l.message} secondary={l.time} primaryTypographyProps={{ variant: "body2", fontFamily: "Consolas, monospace", fontSize: 13 }} secondaryTypographyProps={{ variant: "caption", sx: { color: "#6b7280" } }} />
              </ListItem>
            ))}
          </List>
        )}
      </Paper>
    </Box>
  );
}
