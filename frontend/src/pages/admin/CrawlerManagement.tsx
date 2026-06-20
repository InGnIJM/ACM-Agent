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
import StopIcon from "@mui/icons-material/Stop";
import StorageIcon from "@mui/icons-material/Storage";
import Checkbox from "@mui/material/Checkbox";
import FormGroup from "@mui/material/FormGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import LinearProgress from "@mui/material/LinearProgress";
import CircularProgress from "@mui/material/CircularProgress";
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

  // Bulk crawl state
  const [bulkJobId, setBulkJobId] = useState<string | null>(null);
  const [bulkProgress, setBulkProgress] = useState<any>(null);
  const [bulkPolling, setBulkPolling] = useState(false);
  const [bulkPhases, setBulkPhases] = useState<string[]>(["list", "detail", "solutions"]);
  const [bulkCount, setBulkCount] = useState(1000);
  const [bulkPlatform, setBulkPlatform] = useState<string>("luogu");
  const [bulkTag, setBulkTag] = useState("");
  const [elapsedDisplay, setElapsedDisplay] = useState("");

  // Vector embedding task result (本次爬取任务的嵌入状态)
  const [taskEmbed, setTaskEmbed] = useState<{
    platform: string; action: string; crawled: number; imported: number; time: string;
    importedDetail?: { problems: number; solutions: number; records: number } | null;
  } | null>(null);
  const [vectorSummaryPending, setVectorSummaryPending] = useState(false);

  // Embed progress tracking
  const [embedJobId, setEmbedJobId] = useState<string | null>(null);
  const [embedProgress, setEmbedProgress] = useState<{
    embedTotal: number; embedDone: number; done: boolean;
  } | null>(null);

  // Poll embed progress every 2s while a job is active
  useEffect(() => {
    if (!embedJobId || embedProgress?.done) return;
    const timer = setInterval(async () => {
      try {
        const resp = await api.get(`/crawler/embed-progress/${embedJobId}`);
        const data = resp.data;
        setEmbedProgress({ embedTotal: data.embedTotal, embedDone: data.embedDone, done: data.done });
        if (data.done) {
          setEmbedJobId(null);
          addLog(`[${data.platform}] 向量嵌入完成！${data.embedDone}/${data.embedTotal} 条`, "success");
        }
      } catch { /* silently ignore */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [embedJobId, embedProgress?.done]);

  async function handleSummarize(platform: string) {
    setVectorSummaryPending(true);
    try {
      addLog(`[${platform}] 开始生成摘要和向量嵌入...`);
      const resp = await api.post(`/crawler/summarize/${platform}`);
      const d = resp.data as any;
      addLog(`[${platform}] 摘要任务已启动`, "success");
      // Track progress via embedJobId
      if (d.embedJobId) {
        setEmbedJobId(d.embedJobId);
        setEmbedProgress(null);
      }
      setTaskEmbed(prev => prev ? { ...prev, action: `${prev.action}+embed` } : null);
    } catch (e: any) {
      addLog(`[${platform}] 摘要失败: ${e.message ?? String(e)}`, "error");
    } finally {
      setVectorSummaryPending(false);
    }
  }

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
    setEmbedJobId(null); // 清理旧嵌入进度
    setEmbedProgress(null);
    const act = ACTIONS.find(a => a.value === action);
    addLog(`[${platform}] 开始: ${act?.label ?? action} (count=${count})`);

    try {
      const resp = await api.post("/crawler/trigger/problems", {
        platform, action, uid: uid || undefined, tags: tag || undefined, count,
      }, { timeout: 600_000 }); // 10 min timeout for crawl + import (matches backend 5min + margin)

      const d = resp.data as any;
      if (d.success === false) {
        addLog(`[${platform}] 失败: ${d.platform} 未知平台`, "error");
      } else {
        const detail = d.importedDetail || {};
        const problemPart = detail.problems > 0 ? `题目 ${detail.problems} 题` : '';
        const solutionPart = detail.solutions > 0 ? `题解 ${detail.solutions} 条` : '';
        const recordPart = detail.records > 0 ? `提交记录 ${detail.records} 条` : '';
        const importedParts = [problemPart, solutionPart, recordPart].filter(Boolean).join('，');
        const importedMsg = importedParts ? ` | 入库: ${importedParts}` : '';
        addLog(`[${platform}] 完成: 爬取 ${d.count ?? '?'} 题${importedMsg}`, "success");
        // 记录本次任务嵌入状态
        setTaskEmbed({
          platform: d.platform || platform,
          action: d.action || action,
          crawled: d.count ?? 0,
          imported: d.imported ?? 0,
          importedDetail: d.importedDetail || null,
          time: new Date().toLocaleTimeString(),
        });
        // 开始轮询嵌入进度
        if (d.embedJobId) {
          setEmbedJobId(d.embedJobId);
          setEmbedProgress(null);
        }
        if (d.imported > 0) {
          addLog(`[${platform}] 向量嵌入已自动开始（后台异步生成）`, "info");
        }
        if (d.titles) {
          addLog(`[${platform}] 题目: ${d.titles}`, "info");
        } else if (d.count === 0) {
          addLog(`[${platform}] 未获取到题目（API可能限流或标签无结果）`, "error");
        }
      }
    } catch (e: any) {
      addLog(`[${platform}] 错误: ${e.message ?? String(e)}`, "error");
    }
    setRunning(false);
  }

  function clearLogs() { setLogs([]); }

  // ── Bulk crawl ──────────────────────────────────────────────

  function toggleBulkPhase(phase: string) {
    setBulkPhases((prev) =>
      prev.includes(phase) ? prev.filter((p) => p !== phase) : [...prev, phase]
    );
  }

  async function startBulkCrawl() {
    if (bulkPolling) return;
    setBulkPolling(true);
    setBulkProgress(null);
    setEmbedJobId(null); // 清理旧嵌入进度
    setEmbedProgress(null);
    addLog(`[${bulkPlatform}] 启动批量爬取 (count=${bulkCount}, phases=${bulkPhases.join(",")})`);

    try {
      const resp = await api.post("/crawler/bulk/start", {
        platform: bulkPlatform,
        tags: bulkTag || undefined,
        count: bulkCount,
        phases: bulkPhases,
        skipExisting: true,
      });
      const { jobId } = resp.data;
      setBulkJobId(jobId);
      addLog(`[${bulkPlatform}] 批量任务已创建: ${jobId}`, "success");
    } catch (e: any) {
      addLog(`[${bulkPlatform}] 启动批量爬取失败: ${e.response?.data?.message || e.message || String(e)}`, "error");
      setBulkPolling(false);
    }
  }

  async function cancelBulkCrawl() {
    if (!bulkJobId) return;
    try {
      await api.post(`/crawler/bulk/${bulkJobId}/cancel`);
      addLog(`[${platform}] 已请求取消批量任务`, "info");
    } catch (e: any) {
      addLog(`[${platform}] 取消失败: ${e.message ?? String(e)}`, "error");
    }
  }

  // Poll bulk progress every 2 seconds when a job is running
  useEffect(() => {
    if (!bulkJobId) return;
    const timer = setInterval(async () => {
      try {
        const resp = await api.get(`/crawler/bulk/${bulkJobId}/progress`);
        const data = resp.data;
        setBulkProgress(data);

        // Update elapsed time display
        if (data.elapsed != null) {
          const h = Math.floor(data.elapsed / 3600);
          const m = Math.floor((data.elapsed % 3600) / 60);
          const s = data.elapsed % 60;
          setElapsedDisplay(h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`);
        }

        if (data.status === "completed") {
          addLog(`[${bulkPlatform}] 批量爬取完成！${data.summary?.total_problems ?? "?"} 题`, "success");
          // 记录本次批量任务嵌入状态
          const imported = data.summary?.imported ?? 0;
          setTaskEmbed({
            platform: bulkPlatform,
            action: "bulk_crawl",
            crawled: data.summary?.total_problems ?? 0,
            imported,
            time: new Date().toLocaleTimeString(),
          });
          if (imported > 0) {
            addLog(`[${bulkPlatform}] 已导入 ${imported} 条，向量嵌入自动开始`, "info");
            // Start embed progress polling (bulk crawl's jobId doubles as embedJobId)
            setEmbedJobId(data.jobId);
            setEmbedProgress(null);
          }
          setBulkPolling(false);
          clearInterval(timer);
        } else if (data.status === "failed" || data.status === "cancelled") {
          addLog(`[${bulkPlatform}] 批量爬取${data.status === "cancelled" ? "已取消" : "失败"}`, "error");
          setBulkPolling(false);
          clearInterval(timer);
        }
      } catch {
        // Silently ignore polling errors
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [bulkJobId]);

  // Reset bulk state when completed
  function resetBulk() {
    setBulkJobId(null);
    setBulkProgress(null);
    setBulkPolling(false);
    setElapsedDisplay("");
    // 嵌入进度可能还在跑，重置嵌入状态由 embedJobId useEffect 自动处理
  }

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

      {/* 向量嵌入状态 — 本次任务 */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          <StorageIcon fontSize="small" sx={{ mr: 0.5, verticalAlign: "middle" }} />
          向量嵌入状态（RAG）
        </Typography>
        {taskEmbed ? (
          <Box>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={8}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                  <Chip label={taskEmbed.platform} size="small" color="primary" variant="outlined" />
                  <Typography variant="body2">
                    爬取 <strong>{taskEmbed.crawled}</strong> 题
                    {taskEmbed.importedDetail ? (
                      <>，入库: 题目 <strong>{taskEmbed.importedDetail.problems}</strong> 题
                      {taskEmbed.importedDetail.solutions > 0 && <>，题解 <strong>{taskEmbed.importedDetail.solutions}</strong> 条</>}
                      {taskEmbed.importedDetail.records > 0 && <>，提交记录 <strong>{taskEmbed.importedDetail.records}</strong> 条</>}
                      </>
                    ) : (
                      <>，入库 <strong>{taskEmbed.imported}</strong> 条</>
                    )}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {taskEmbed.time}
                  </Typography>
                </Box>
                <Box sx={{ mt: 1 }}>
                  {embedProgress ? (
                    embedProgress.embedTotal > 0 ? (
                      <Box>
                        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
                          <Typography variant="body2" color="text.secondary">
                            {embedProgress.done
                              ? "向量嵌入已完成"
                              : `向量嵌入中... ${embedProgress.embedDone}/${embedProgress.embedTotal}`}
                          </Typography>
                          <Typography variant="body2" fontWeight={600}>
                            {embedProgress.embedTotal > 0
                              ? Math.round((embedProgress.embedDone / embedProgress.embedTotal) * 100)
                              : 0}%
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant={embedProgress.done ? "determinate" : "indeterminate"}
                          value={embedProgress.done ? 100 : undefined}
                          color={embedProgress.done ? "success" : "primary"}
                          sx={{ height: 6, borderRadius: 3 }}
                        />
                        {embedProgress.done && (
                          <Alert severity="success" sx={{ mt: 1, py: 0 }}>
                            向量嵌入完成！共处理 {embedProgress.embedDone} 条，现在可以使用 RAG 语义搜索。
                          </Alert>
                        )}
                      </Box>
                    ) : (
                      <Alert severity="info" sx={{ py: 0 }}>
                        暂无未处理的题目，无需生成向量嵌入。
                      </Alert>
                    )
                  ) : taskEmbed.imported > 0 ? (
                    <Alert severity="success" sx={{ py: 0 }}>
                      导入的数据已自动开始生成摘要和向量嵌入（后台异步处理）。
                      向量嵌入完成后即可使用 RAG 语义搜索。
                    </Alert>
                  ) : (
                    <Alert severity="info" sx={{ py: 0 }}>
                      爬取的题目均为已存在数据（跳过重复），无需重新嵌入。
                    </Alert>
                  )}
                </Box>
              </Grid>
              <Grid item xs={12} sm={4} sx={{ textAlign: "right" }}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => handleSummarize(taskEmbed.platform)}
                  disabled={vectorSummaryPending}
                >
                  {vectorSummaryPending ? "嵌入中..." : "手动生成摘要+向量"}
                </Button>
              </Grid>
            </Grid>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">
            执行爬取后系统将自动导入题目并生成向量嵌入。完成后在此查看本次任务的嵌入状态。
          </Typography>
        )}
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

      {/* 批量爬取面板 */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>批量爬取（支持 10 万+ 题目）</Typography>
        <Alert severity="warning" sx={{ mb: 2 }}>
          批量爬取在后台异步运行，可关闭页面。同一平台同时只能运行一个批量任务。预计每 1000 条题目列表约 25 秒，详情约 8 分钟，题解约 25 分钟。
        </Alert>

        {!bulkPolling ? (
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={6} sm={2}>
              <FormControl fullWidth size="small">
                <InputLabel>平台</InputLabel>
                <Select value={bulkPlatform} label="平台"
                  onChange={e => setBulkPlatform(e.target.value)}>
                  {PLATFORMS.map(p => <MenuItem key={p} value={p}>{p}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={6} sm={2}>
              <TextField fullWidth size="small" label="标签（空=全部）" value={bulkTag}
                onChange={e => setBulkTag(e.target.value)}
                placeholder="留空=全部 / P / B / CF" />
            </Grid>

            <Grid item xs={4} sm={1}>
              <TextField fullWidth size="small" label="数量" type="number" value={bulkCount}
                onChange={e => setBulkCount(Number(e.target.value))}
                inputProps={{ min: 1, max: 100000 }} />
            </Grid>

            <Grid item xs={12} sm={3}>
              <FormGroup row>
                {["list", "detail", "solutions"].map(ph => (
                  <FormControlLabel key={ph}
                    control={<Checkbox size="small" checked={bulkPhases.includes(ph)} onChange={() => toggleBulkPhase(ph)} />}
                    label={ph === "list" ? "列表" : ph === "detail" ? "详情" : "题解"} />
                ))}
              </FormGroup>
            </Grid>

            <Grid item xs={6} sm={2}>
              <Button variant="contained" color="secondary" startIcon={<PlayArrowIcon />}
                onClick={startBulkCrawl} disabled={running}>
                开始批量爬取
              </Button>
            </Grid>
          </Grid>
        ) : (
          <Box>
            {/* Progress display */}
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
              <Typography variant="subtitle1">
                {bulkProgress?.status === "completed" ? "✅ 完成" :
                 bulkProgress?.status === "failed" ? "❌ 失败" :
                 bulkProgress?.status === "cancelled" ? "⏹ 已取消" :
                 `🔄 ${bulkProgress?.phase === "list" ? "阶段 1/3: 收集列表" :
                         bulkProgress?.phase === "detail" ? "阶段 2/3: 获取详情" :
                         bulkProgress?.phase === "solutions" ? "阶段 3/3: 获取题解" : "准备中..."}`}
              </Typography>
              <Box sx={{ display: "flex", gap: 2, alignItems: "center" }}>
                {elapsedDisplay && <Typography variant="body2" color="text.secondary">⏱ {elapsedDisplay}</Typography>}
                {bulkProgress?.eta && bulkProgress?.status === "running" && (
                  <Typography variant="body2" color="text.secondary">
                    预计剩余: {(() => {
                      try { const s = Math.floor((new Date(bulkProgress.eta).getTime() - Date.now()) / 1000);
                        if (s <= 0) return "计算中...";
                        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
                        return h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`; } catch { return "计算中..."; }
                    })()}
                  </Typography>
                )}
                {bulkProgress?.status === "running" && (
                  <Button size="small" color="error" startIcon={<StopIcon />} onClick={cancelBulkCrawl}>取消</Button>
                )}
                {(bulkProgress?.status === "completed" || bulkProgress?.status === "failed" || bulkProgress?.status === "cancelled") && (
                  <Button size="small" onClick={resetBulk}>关闭</Button>
                )}
              </Box>
            </Box>

            {/* Phase stepper */}
            <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
              {["list", "detail", "solutions"].map((ph, idx) => {
                const ps = bulkProgress?.phases?.[ph];
                const isActive = bulkProgress?.phase === ph;
                const isDone = ps?.status === "completed";
                const isFailed = ps?.status === "failed";
                let color: "primary" | "success" | "error" | "default" = "default";
                if (isActive) color = "primary";
                else if (isDone) color = "success";
                else if (isFailed) color = "error";
                return (
                  <Chip key={ph}
                    icon={isActive ? <CircularProgress size={14} /> : isDone ? <CheckCircleIcon /> : undefined}
                    label={`${idx + 1}. ${ph === "list" ? "列表" : ph === "detail" ? "详情" : "题解"} ${ps?.fetched != null && ps?.total ? `(${ps.fetched}/${ps.total})` : ""}`}
                    color={color} variant={isActive ? "filled" : "outlined"} size="small" />
                );
              })}
            </Box>

            {/* Progress bar */}
            {(() => {
              const cp = bulkProgress?.phases?.[bulkProgress?.phase as string];
              if (!cp || !cp.total) return null;
              const pct = cp.total > 0 ? Math.round((cp.fetched || 0) / cp.total * 100) : 0;
              return (
                <Box sx={{ mb: 1 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
                    <Typography variant="body2">{bulkProgress?.phase === "list" ? "列表收集" : bulkProgress?.phase === "detail" ? "详情获取" : "题解获取"}</Typography>
                    <Typography variant="body2">{cp.fetched || 0} / {cp.total} ({pct}%)</Typography>
                  </Box>
                  <LinearProgress variant="determinate" value={pct} sx={{ height: 8, borderRadius: 4 }} />
                </Box>
              );
            })()}

            {/* Error count */}
            {bulkProgress?.errors?.length > 0 && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {bulkProgress.errors.length} 个错误（详见日志），已自动跳过继续执行
              </Alert>
            )}
          </Box>
        )}
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
