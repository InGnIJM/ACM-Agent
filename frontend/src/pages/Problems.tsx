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
import useApi from "../hooks/useApi";
import usePagination from "../hooks/usePagination";
import * as problemsApi from "../services/problems";

// Real API response type
interface ProblemItem {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  difficultyNormalized: number;
  tagsPlatform: number[];
}

const DIFF_COLORS: Record<number, string> = { 1: "#22C55E", 2: "#22C55E", 3: "#4ADE80", 4: "#F59E0B", 5: "#F59E0B", 6: "#F97316", 7: "#F97316", 8: "#EF4444", 9: "#EF4444", 10: "#DC2626" };

function diffLabel(v: number): string {
  if (v <= 2) return "入门";
  if (v <= 4) return "普及";
  if (v <= 6) return "提高";
  if (v <= 8) return "省选";
  return "NOI";
}

function diffColor(v: number): string {
  return DIFF_COLORS[Math.round(v)] ?? "#9CA3AF";
}

export default function Problems() {
  const navigate = useNavigate();
  const { page, limit, setPage, setLimit, setTotal, total } = usePagination();

  const queryParams = useMemo(() => ({ page, limit }), [page, limit]);

  const fetcher = useCallback(() => problemsApi.getProblems(queryParams as any), [queryParams]);

  const { data, loading, error } = useApi(fetcher, [JSON.stringify(queryParams)]);

  // API returns { data: ProblemItem[], total: number }
  const problems: ProblemItem[] = (data as any)?.data ?? [];

  // Update total
  if ((data as any)?.total && (data as any).total !== total) {
    setTotal((data as any).total);
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>题库</Typography>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>题号</TableCell>
              <TableCell>标题</TableCell>
              <TableCell width={80}>难度</TableCell>
              <TableCell width={80}>平台</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {[1, 2, 3, 4].map((j) => (
                    <TableCell key={j}><Skeleton /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : problems.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} align="center">
                  <Typography color="text.secondary">{error ?? "暂无题目"}</Typography>
                </TableCell>
              </TableRow>
            ) : (
              problems.map((p) => (
                <TableRow key={p.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/problems/${p.id}`)}>
                  <TableCell>{p.sourceId}</TableCell>
                  <TableCell>{p.title}</TableCell>
                  <TableCell>
                    <Chip label={diffLabel(p.difficultyNormalized)} size="small" sx={{ bgcolor: diffColor(p.difficultyNormalized), color: "#fff", fontWeight: 600 }} />
                  </TableCell>
                  <TableCell>{p.sourcePlatform}</TableCell>
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
