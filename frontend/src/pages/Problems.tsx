import { useState, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TablePagination from "@mui/material/TablePagination";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import IconButton from "@mui/material/IconButton";
import Checkbox from "@mui/material/Checkbox";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Alert from "@mui/material/Alert";
import DeleteIcon from "@mui/icons-material/Delete";
import SearchIcon from "@mui/icons-material/Search";
import PsychologyIcon from "@mui/icons-material/Psychology";
import useApi from "../hooks/useApi";
import usePagination from "../hooks/usePagination";
import * as problemsApi from "../services/problems";
import type { Problem, ProblemListQuery, VectorSearchResultItem } from "../types/problem";

const PLATFORM_LABELS: Record<string, string> = {
  luogu: "洛谷",
  leetcode: "LeetCode",
  codeforces: "Codeforces",
  nowcoder: "牛客",
  atcoder: "AtCoder",
};

const PLATFORMS = ["luogu", "leetcode", "codeforces", "nowcoder", "atcoder"];

const DIFF_RANGES = [
  { label: "全部难度", min: 0, max: 3500 },
  { label: "入门 (0-999)", min: 0, max: 999 },
  { label: "普及 (1000-1699)", min: 1000, max: 1699 },
  { label: "提高 (1700-2399)", min: 1700, max: 2399 },
  { label: "省选/NOI (2400+)", min: 2400, max: 3500 },
];

function diffLabel(v: number): string {
  if (v <= 999) return "入门";
  if (v <= 1699) return "普及";
  if (v <= 2399) return "提高";
  if (v <= 3499) return "省选";
  return "NOI";
}

const DIFF_COLORS: Record<number, string> = {
  1: "#22C55E", 2: "#22C55E", 3: "#4ADE80",
  4: "#F59E0B", 5: "#F59E0B", 6: "#F97316",
  7: "#F97316", 8: "#EF4444", 9: "#EF4444", 10: "#DC2626",
};

function diffColor(v: number): string {
  return DIFF_COLORS[Math.round(v)] ?? "#9CA3AF";
}

export default function Problems() {
  const navigate = useNavigate();
  const { page, limit, setPage, setLimit, setTotal, total } = usePagination();

  // ── Filters ──────────────────────────────────────────────
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState("");
  const [diffRange, setDiffRange] = useState(0);
  const [tagFilter, setTagFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // ── Vector search ──────────────────────────────────────
  const [searchMode, setSearchMode] = useState<"normal" | "vector">("normal");
  const [vectorQuery, setVectorQuery] = useState("");
  const [vectorLoading, setVectorLoading] = useState(false);
  const [vectorResults, setVectorResults] = useState<VectorSearchResultItem[] | null>(null);
  const [vectorError, setVectorError] = useState("");

  const doVectorSearch = async () => {
    if (!vectorQuery.trim()) return;
    setVectorLoading(true);
    setVectorError("");
    try {
      const resp = await problemsApi.searchByVector({
        query: vectorQuery.trim(),
        topK: 20,
        platform: platform || undefined,
        difficultyMin: diffCfg.min > 0 ? diffCfg.min : undefined,
        difficultyMax: diffCfg.max < 3500 ? diffCfg.max : undefined,
      });
      setVectorResults(resp.results);
    } catch (e: any) {
      setVectorError(e?.message || "向量搜索失败");
      setVectorResults(null);
    } finally {
      setVectorLoading(false);
    }
  };

  const diffCfg = DIFF_RANGES[diffRange] ?? DIFF_RANGES[0];

  const queryParams: ProblemListQuery = useMemo(() => ({
    page,
    limit,
    search: search || undefined,
    platform: platform || undefined,
    difficultyMin: diffCfg.min > 0 ? diffCfg.min : undefined,
    difficultyMax: diffCfg.max < 3500 ? diffCfg.max : undefined,
    tags: tagFilter ? [tagFilter] : undefined,
  }), [page, limit, search, platform, diffCfg, tagFilter]);

  const fetcher = useCallback(
    () => problemsApi.getProblems(queryParams),
    [JSON.stringify(queryParams)],
  );

  const { data, loading, error } = useApi(fetcher, [JSON.stringify(queryParams)]);

  const problems: Problem[] = (data as any)?.data ?? [];

  if ((data as any)?.total !== undefined && (data as any).total !== total) {
    setTotal((data as any).total);
  }

  // ── Delete handlers ──────────────────────────────────────

  const [deleteDialog, setDeleteDialog] = useState<{ open: boolean; ids: string[]; title: string }>({
    open: false, ids: [], title: "",
  });

  const confirmDelete = (ids: string[], title: string) => {
    setDeleteDialog({ open: true, ids, title });
  };

  const doDelete = async () => {
    const ids = deleteDialog.ids;
    try {
      if (ids.length === 1) {
        await problemsApi.deleteProblem(ids[0]);
      } else {
        await problemsApi.batchDeleteProblems(ids);
      }
      // Reset and refetch
      setSelected(new Set());
      setDeleteDialog({ open: false, ids: [], title: "" });
      // Force refetch by changing a dep — simplest: reload
      window.location.reload();
    } catch (e: any) {
      console.error("Delete failed:", e);
      alert(`删除失败: ${e?.message || e}`);
    }
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const toggleAll = () => {
    if (selected.size === problems.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(problems.map((p) => p.id)));
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>题库</Typography>

      {/* ── Search mode toggle ──────────────────────── */}
      <ToggleButtonGroup
        value={searchMode}
        exclusive
        onChange={(_, v) => v && setSearchMode(v)}
        size="small"
        sx={{ mb: 1 }}
      >
        <ToggleButton value="normal">关键词搜索</ToggleButton>
        <ToggleButton value="vector">
          <PsychologyIcon fontSize="small" sx={{ mr: 0.5 }} />
          语义搜索
        </ToggleButton>
      </ToggleButtonGroup>

      {/* ── Search & Filters ──────────────────────────── */}
      <Stack direction="row" spacing={2} sx={{ mb: 2 }} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          placeholder="搜索标题…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          InputProps={{ startAdornment: <SearchIcon sx={{ mr: 0.5, color: "text.secondary" }} /> }}
          sx={{ minWidth: 220 }}
        />

        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>平台</InputLabel>
          <Select
            value={platform}
            label="平台"
            onChange={(e) => { setPlatform(e.target.value); setPage(1); }}
          >
            <MenuItem value="">全部平台</MenuItem>
            {PLATFORMS.map((p) => (
              <MenuItem key={p} value={p}>{PLATFORM_LABELS[p] ?? p}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>难度</InputLabel>
          <Select
            value={String(diffRange)}
            label="难度"
            onChange={(e) => { setDiffRange(Number(e.target.value)); setPage(1); }}
          >
            {DIFF_RANGES.map((r, i) => (
              <MenuItem key={i} value={String(i)}>{r.label}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <TextField
          size="small"
          placeholder="标签筛选…"
          value={tagFilter}
          onChange={(e) => { setTagFilter(e.target.value); setPage(1); }}
          sx={{ minWidth: 140 }}
        />

        {selected.size > 0 && (
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteIcon />}
            onClick={() => confirmDelete([...selected], `${selected.size} 个题目`)}
          >
            删除选中 ({selected.size})
          </Button>
        )}
      </Stack>

      {/* ── Vector search bar & results ──────────────── */}
      {searchMode === "vector" && (
        <Box sx={{ mb: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              size="small"
              placeholder="用自然语言描述你想找的题目…"
              value={vectorQuery}
              onChange={(e) => setVectorQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doVectorSearch()}
              sx={{ flex: 1 }}
              InputProps={{
                startAdornment: <PsychologyIcon sx={{ mr: 0.5, color: "primary.main" }} />,
              }}
            />
            <Button
              variant="contained"
              onClick={doVectorSearch}
              disabled={vectorLoading || !vectorQuery.trim()}
            >
              {vectorLoading ? "搜索中…" : "搜索"}
            </Button>
          </Stack>
          {vectorError && (
            <Alert severity="error" sx={{ mt: 1 }} onClose={() => setVectorError("")}>
              {vectorError}
            </Alert>
          )}
          {vectorResults && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                找到 {vectorResults.length} 个结果
              </Typography>
              <TableContainer component={Paper}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>题号</TableCell>
                      <TableCell>标题</TableCell>
                      <TableCell width={80}>难度</TableCell>
                      <TableCell width={80}>平台</TableCell>
                      <TableCell width={140}>标签</TableCell>
                      <TableCell width={70} align="right">相似度</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {vectorResults.map((r) => (
                      <TableRow key={r.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/problems/${r.id}`)}>
                        <TableCell>{r.sourceId}</TableCell>
                        <TableCell>{r.title}</TableCell>
                        <TableCell>
                          <Chip label={diffLabel(r.difficultyNormalized)} size="small" sx={{ bgcolor: diffColor(r.difficultyNormalized), color: "#fff", fontWeight: 600 }} />
                        </TableCell>
                        <TableCell>{PLATFORM_LABELS[r.sourcePlatform] ?? r.sourcePlatform}</TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                            {(r.tagsNormalized ?? []).slice(0, 3).map((t) => (
                              <Chip key={t} label={t} size="small" variant="outlined" sx={{ fontSize: "0.7rem" }} />
                            ))}
                          </Stack>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="body2" color={r.similarity > 0.7 ? "success.main" : "text.secondary"}>
                            {(r.similarity * 100).toFixed(1)}%
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </Box>
      )}

      {/* ── Table ──────────────────────────────────────── */}
      {searchMode === "normal" && (
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  indeterminate={selected.size > 0 && selected.size < problems.length}
                  checked={problems.length > 0 && selected.size === problems.length}
                  onChange={toggleAll}
                />
              </TableCell>
              <TableCell>题号</TableCell>
              <TableCell>标题</TableCell>
              <TableCell width={80}>难度</TableCell>
              <TableCell width={80}>平台</TableCell>
              <TableCell width={160}>标签</TableCell>
              <TableCell width={50} align="center">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {[1, 2, 3, 4, 5, 6, 7].map((j) => (
                    <TableCell key={j}><Skeleton /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : problems.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography color="text.secondary">{error ?? "暂无题目"}</Typography>
                </TableCell>
              </TableRow>
            ) : (
              problems.map((p) => (
                <TableRow key={p.id} hover sx={{ cursor: "pointer" }}>
                  <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selected.has(p.id)}
                      onChange={() => toggleSelect(p.id)}
                    />
                  </TableCell>
                  <TableCell onClick={() => navigate(`/problems/${p.id}`)}>{p.sourceId}</TableCell>
                  <TableCell onClick={() => navigate(`/problems/${p.id}`)}>{p.title}</TableCell>
                  <TableCell onClick={() => navigate(`/problems/${p.id}`)}>
                    <Chip
                      label={diffLabel(p.difficultyNormalized)}
                      size="small"
                      sx={{ bgcolor: diffColor(p.difficultyNormalized), color: "#fff", fontWeight: 600 }}
                    />
                  </TableCell>
                  <TableCell onClick={() => navigate(`/problems/${p.id}`)}>
                    {PLATFORM_LABELS[p.sourcePlatform] ?? p.sourcePlatform}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {(p.tagsNormalized ?? []).slice(0, 4).map((t) => (
                        <Chip key={t} label={t} size="small" variant="outlined" sx={{ fontSize: "0.7rem" }} />
                      ))}
                      {(p.tagsNormalized ?? []).length > 4 && (
                        <Chip label={`+${p.tagsNormalized.length - 4}`} size="small" sx={{ fontSize: "0.7rem" }} />
                      )}
                    </Stack>
                  </TableCell>
                  <TableCell align="center" onClick={(e) => e.stopPropagation()}>
                    <Tooltip title="删除">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => confirmDelete([p.id], p.title)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={total}
          page={page - 1}
          rowsPerPage={limit}
          onPageChange={(_, p) => setPage(p + 1)}
          onRowsPerPageChange={(e) => setLimit(Number(e.target.value))}
          rowsPerPageOptions={[10, 20, 50]}
          labelRowsPerPage="每页行数"
        />
      </TableContainer>

      )}
      {/* ── Delete confirmation dialog ─────────────────── */}
      <Dialog open={deleteDialog.open} onClose={() => setDeleteDialog({ open: false, ids: [], title: "" })}>
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {deleteDialog.ids.length === 1
              ? `确定要删除「${deleteDialog.title}」吗？此操作不可撤销。`
              : `确定要删除 ${deleteDialog.ids.length} 个题目吗？此操作不可撤销。`}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialog({ open: false, ids: [], title: "" })}>取消</Button>
          <Button onClick={doDelete} color="error" variant="contained">确认删除</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
