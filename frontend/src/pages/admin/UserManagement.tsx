// ============================================================
// Admin: UserManagement — data table of all users, search+filter,
// edit/delete row actions.
// ============================================================

import { useState, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TablePagination from "@mui/material/TablePagination";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import useApi from "../../hooks/useApi";
import usePagination from "../../hooks/usePagination";
import useDebounce from "../../hooks/useDebounce";
import * as usersApi from "../../services/users";
import type { User } from "../../types/user";
import type { PaginatedResponse } from "../../types/api";

export default function UserManagement() {
  const navigate = useNavigate();
  const [searchText, setSearchText] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const debouncedSearch = useDebounce(searchText, 300);
  const { page, limit, setPage, setLimit, setTotal, total, reset } =
    usePagination();
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  const query = useMemo(
    () => ({
      page,
      limit,
      ...(debouncedSearch ? { search: debouncedSearch } : {}),
      ...(roleFilter ? { role: roleFilter } : {}),
    }),
    [page, limit, debouncedSearch, roleFilter],
  );

  const fetcher = useCallback(
    () => usersApi.getUsers(query),
    [query],
  );

  const { data, loading, error, refetch } = useApi<PaginatedResponse<User>>(
    fetcher,
    [JSON.stringify(query)],
  );

  const users = (data as any)?.data ?? [];

  if (data && data.total !== total) {
    setTotal(data.total);
  }

  function handleFilterChange() {
    reset();
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await usersApi.deleteUser(deleteTarget.id);
      setDeleteTarget(null);
      refetch();
    } catch {
      // Swallow — handled by error state
    }
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        用户管理 (管理员)
      </Typography>

      {/* ---- filters ---- */}
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 2 }}>
        <TextField
          size="small"
          label="搜索用户名/邮箱"
          value={searchText}
          onChange={(e) => {
            setSearchText(e.target.value);
            handleFilterChange();
          }}
          sx={{ minWidth: 200 }}
        />
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>角色</InputLabel>
          <Select
            value={roleFilter}
            label="角色"
            onChange={(e) => {
              setRoleFilter(e.target.value);
              handleFilterChange();
            }}
          >
            <MenuItem value="">全部</MenuItem>
            <MenuItem value="admin">管理员</MenuItem>
            <MenuItem value="user">普通用户</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* ---- table ---- */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>用户名</TableCell>
              <TableCell>邮箱</TableCell>
              <TableCell>昵称</TableCell>
              <TableCell width={90}>角色</TableCell>
              <TableCell>学号</TableCell>
              <TableCell width={120}>操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {[1, 2, 3, 4, 5, 6, 7].map((j) => (
                    <TableCell key={j}>
                      <Skeleton />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : error ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography color="error">{error}</Typography>
                </TableCell>
              </TableRow>
            ) : users.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Typography color="text.secondary">暂无用户</Typography>
                </TableCell>
              </TableRow>
            ) : (
              users.map((u) => (
                <TableRow key={u.id} hover>
                  <TableCell>{u.id}</TableCell>
                  <TableCell>{u.username}</TableCell>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>{u.nickname ?? "-"}</TableCell>
                  <TableCell>
                    <Chip
                      label={u.role === "admin" ? "管理员" : "用户"}
                      size="small"
                      color={u.role === "admin" ? "primary" : "default"}
                    />
                  </TableCell>
                  <TableCell>{u.studentId ?? "-"}</TableCell>
                  <TableCell>
                    <Tooltip title="编辑">
                      <IconButton
                        size="small"
                        onClick={() => navigate(`/admin/users/${u.id}`)}
                      >
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="删除">
                      <IconButton
                        size="small"
                        onClick={() => setDeleteTarget(u)}
                      >
                        <DeleteIcon fontSize="small" color="error" />
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

      {/* ---- delete confirmation dialog ---- */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          确定要删除用户 "{deleteTarget?.username}" 吗？此操作不可撤销。
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>取消</Button>
          <Button onClick={handleDelete} color="error" variant="contained">
            删除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
