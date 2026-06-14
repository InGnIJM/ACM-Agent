// ============================================================
// Records page — submission records table with verdict badges,
// language, platform. Supports filtering by status/difficulty.
// ============================================================

import { useState, useMemo, useCallback } from "react";
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
import FormControl from "@mui/material/FormControl";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import Skeleton from "@mui/material/Skeleton";
import useApi from "../hooks/useApi";
import usePagination from "../hooks/usePagination";
import * as recordsApi from "../services/records";
import type { SubmissionRecord, RecordStatus, RecordListQuery } from "../types/record";

const STATUS_COLORS: Record<string, string> = {
  accepted: "#22C55E",
  wrong_answer: "#EF4444",
  time_limit: "#F59E0B",
  memory_limit: "#F59E0B",
  runtime_error: "#EF4444",
  compilation_error: "#8B5CF6",
  pending: "#9CA3AF",
};

const STATUS_LABELS: Record<string, string> = {
  accepted: "AC",
  wrong_answer: "WA",
  time_limit: "TLE",
  memory_limit: "MLE",
  runtime_error: "RE",
  compilation_error: "CE",
  pending: "Pending",
};

export default function Records() {
  const [status, setStatus] = useState<RecordStatus | "">("");
  const [difficulty, setDifficulty] = useState("");
  const { page, limit, setPage, setLimit, setTotal, total, reset } =
    usePagination();

  const query = useMemo<RecordListQuery>(
    () => ({
      page,
      page_size: limit,
      ...(status ? { status: status as RecordStatus } : {}),
      ...(difficulty ? { difficulty } : {}),
    }),
    [page, limit, status, difficulty],
  );

  const fetcher = useCallback(
    () => recordsApi.getRecords(query),
    [query],
  );

  const { data, loading, error } = useApi(fetcher, [JSON.stringify(query)]);

  if (data && data.total !== total) {
    setTotal(data.total);
  }

  const records: SubmissionRecord[] = data?.items ?? [];

  function handleFilterChange() {
    reset();
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        提交记录
      </Typography>

      {/* ---- filters ---- */}
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>状态</InputLabel>
          <Select
            value={status}
            label="状态"
            onChange={(e) => {
              setStatus(e.target.value as RecordStatus | "");
              handleFilterChange();
            }}
          >
            <MenuItem value="">全部</MenuItem>
            <MenuItem value="accepted">AC</MenuItem>
            <MenuItem value="wrong_answer">WA</MenuItem>
            <MenuItem value="time_limit">TLE</MenuItem>
            <MenuItem value="memory_limit">MLE</MenuItem>
            <MenuItem value="runtime_error">RE</MenuItem>
            <MenuItem value="compilation_error">CE</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>难度</InputLabel>
          <Select
            value={difficulty}
            label="难度"
            onChange={(e) => {
              setDifficulty(e.target.value);
              handleFilterChange();
            }}
          >
            <MenuItem value="">全部</MenuItem>
            <MenuItem value="easy">简单</MenuItem>
            <MenuItem value="medium">中等</MenuItem>
            <MenuItem value="hard">困难</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>题目</TableCell>
              <TableCell width={80}>状态</TableCell>
              <TableCell width={90}>语言</TableCell>
              <TableCell>平台</TableCell>
              <TableCell width={100}>难度</TableCell>
              <TableCell width={180}>提交时间</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {[1, 2, 3, 4, 5, 6].map((j) => (
                    <TableCell key={j}>
                      <Skeleton />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : error ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography color="error">{error}</Typography>
                </TableCell>
              </TableRow>
            ) : records.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography color="text.secondary">暂无记录</Typography>
                </TableCell>
              </TableRow>
            ) : (
              records.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.problem_title ?? `#${r.problem_id}`}</TableCell>
                  <TableCell>
                    <Chip
                      label={STATUS_LABELS[r.status] ?? r.status}
                      size="small"
                      sx={{
                        bgcolor:
                          STATUS_COLORS[r.status] ?? STATUS_COLORS.pending,
                        color: "#fff",
                        fontWeight: 600,
                      }}
                    />
                  </TableCell>
                  <TableCell>{r.language}</TableCell>
                  <TableCell>{r.platform}</TableCell>
                  <TableCell>
                    <Chip
                      label={r.difficulty}
                      size="small"
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>
                    {new Date(r.submitted_at).toLocaleString()}
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
    </Box>
  );
}
