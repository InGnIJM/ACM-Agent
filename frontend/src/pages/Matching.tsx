// ============================================================
// Matching page — compatibility matrix, top-3 teammate combos,
// create team button.
// ============================================================

import { useMemo, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActions from "@mui/material/CardActions";
import Avatar from "@mui/material/Avatar";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import LinearProgress from "@mui/material/LinearProgress";
import useApi from "../hooks/useApi";
import useAuth from "../hooks/useAuth";
import * as matchingApi from "../services/matching";
import type { MatchProfile } from "../types/team";

function stringToColor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00ffffff).toString(16).toUpperCase();
  return "#" + "00000".substring(0, 6 - c.length) + c;
}

export default function Matching() {
  const { user } = useAuth();
  const userId = user?.id ?? 0;

  const fetcher = useCallback(
    () => matchingApi.recommend(userId),
    [userId],
  );

  const { data: matches, loading, error } = useApi<MatchProfile[]>(fetcher, [
    userId,
  ]);

  const top3 = (matches ?? []).slice(0, 3);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        匹配组队
      </Typography>

      {loading ? (
        <Box sx={{ p: 3 }}>
          <Skeleton variant="text" width={300} />
          <Skeleton variant="rectangular" height={200} sx={{ mt: 2 }} />
        </Box>
      ) : error ? (
        <Alert severity="error">{error}</Alert>
      ) : !matches || matches.length === 0 ? (
        <Alert severity="info">
          暂无推荐队友，请先完成一些题目来获得更精准的匹配。
        </Alert>
      ) : (
        <>
          {/* ---- top 3 recommended combos ---- */}
          <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
            推荐组合 (Top 3)
          </Typography>
          <Grid container spacing={2} sx={{ mb: 4 }}>
            {top3.map((m, idx) => (
              <Grid item xs={12} md={4} key={m.user_id}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                      <Avatar
                        sx={{ bgcolor: stringToColor(m.username) }}
                      >
                        {(m.nickname ?? m.username).charAt(0).toUpperCase()}
                      </Avatar>
                      <Box>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {m.nickname ?? m.username}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          #{idx + 1} 推荐
                        </Typography>
                      </Box>
                    </Box>

                    <Typography variant="body2" gutterBottom>
                      匹配度: {(m.score * 100).toFixed(0)}%
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={m.score * 100}
                      sx={{ mb: 1.5, height: 8, borderRadius: 4 }}
                    />

                    <Box sx={{ mb: 1 }}>
                      <Typography variant="caption" color="text.secondary">
                        已通过: {m.solved_count} 题
                      </Typography>
                    </Box>

                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mb: 1 }}>
                      {(m.strengths ?? []).map((s) => (
                        <Chip key={s} label={s} size="small" color="success" variant="outlined" />
                      ))}
                    </Box>
                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                      {(m.weaknesses ?? []).map((w) => (
                        <Chip key={w} label={w} size="small" color="error" variant="outlined" />
                      ))}
                    </Box>
                  </CardContent>
                  <CardActions>
                    <Button size="small">邀请组队</Button>
                  </CardActions>
                </Card>
              </Grid>
            ))}
          </Grid>

          {/* ---- compatibility matrix ---- */}
          <Paper sx={{ p: 2, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              兼容性矩阵
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>用户名</TableCell>
                    <TableCell>通过数</TableCell>
                    <TableCell>匹配度</TableCell>
                    <TableCell>优势</TableCell>
                    <TableCell>薄弱</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {matches.map((m) => (
                    <TableRow key={m.user_id}>
                      <TableCell>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                          <Avatar sx={{ width: 28, height: 28, fontSize: 14, bgcolor: stringToColor(m.username) }}>
                            {(m.nickname ?? m.username).charAt(0).toUpperCase()}
                          </Avatar>
                          {m.nickname ?? m.username}
                        </Box>
                      </TableCell>
                      <TableCell>{m.solved_count}</TableCell>
                      <TableCell>
                        <Chip
                          label={`${(m.score * 100).toFixed(0)}%`}
                          size="small"
                          color={m.score > 0.7 ? "success" : m.score > 0.4 ? "primary" : "default"}
                        />
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                          {m.strengths.slice(0, 3).map((s) => (
                            <Chip key={s} label={s} size="small" variant="outlined" color="success" />
                          ))}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                          {m.weaknesses.slice(0, 3).map((w) => (
                            <Chip key={w} label={w} size="small" variant="outlined" color="error" />
                          ))}
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          <Box sx={{ textAlign: "center" }}>
            <Button
              variant="contained"
              size="large"
              onClick={() => {
                // create team flow — navigate to team creation
              }}
            >
              创建新队伍
            </Button>
          </Box>
        </>
      )}
    </Box>
  );
}
