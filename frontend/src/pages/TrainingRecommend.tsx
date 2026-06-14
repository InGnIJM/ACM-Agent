// ============================================================
// TrainingRecommend — quick problem recommendations, filterable
// by tag/difficulty, displayed as problem cards.
// ============================================================

import { useState, useMemo, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActions from "@mui/material/CardActions";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import TextField from "@mui/material/TextField";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import LaunchIcon from "@mui/icons-material/Launch";
import useApi from "../hooks/useApi";
import useDebounce from "../hooks/useDebounce";
import useAuth from "../hooks/useAuth";
import * as trainingApi from "../services/training";
import type { RecommendedProblem } from "../types/training";

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: "#22C55E",
  medium: "#F59E0B",
  hard: "#EF4444",
};

export default function TrainingRecommend() {
  const { user } = useAuth();
  const userId = user?.id ?? 0;
  const [difficultyFilter, setDifficultyFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const debouncedTag = useDebounce(tagFilter, 300);

  const fetcher = useCallback(
    () => trainingApi.getRecommend(userId),
    [userId],
  );

  const {
    data: result,
    loading,
    error,
  } = useApi(fetcher, [userId]);

  const filtered = useMemo(() => {
    if (!result?.items) return [];
    return result.items.filter((p) => {
      if (difficultyFilter && p.difficulty !== difficultyFilter) return false;
      if (
        debouncedTag &&
        !p.tags.some((t) =>
          t.toLowerCase().includes(debouncedTag.toLowerCase()),
        )
      )
        return false;
      return true;
    });
  }, [result, difficultyFilter, debouncedTag]);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        题目推荐
      </Typography>

      {/* ---- filters ---- */}
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 3 }}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>难度</InputLabel>
          <Select
            value={difficultyFilter}
            label="难度"
            onChange={(e) => setDifficultyFilter(e.target.value)}
          >
            <MenuItem value="">全部</MenuItem>
            <MenuItem value="easy">简单</MenuItem>
            <MenuItem value="medium">中等</MenuItem>
            <MenuItem value="hard">困难</MenuItem>
          </Select>
        </FormControl>

        <TextField
          size="small"
          label="标签筛选"
          value={tagFilter}
          onChange={(e) => setTagFilter(e.target.value)}
        />
      </Box>

      {loading ? (
        <Grid container spacing={2}>
          {[1, 2, 3, 4].map((n) => (
            <Grid item xs={12} sm={6} md={4} lg={3} key={n}>
              <Skeleton variant="rectangular" height={160} />
            </Grid>
          ))}
        </Grid>
      ) : error ? (
        <Alert severity="error">{error}</Alert>
      ) : filtered.length === 0 ? (
        <Alert severity="info">暂无符合条件的推荐题目</Alert>
      ) : (
        <Grid container spacing={2}>
          {filtered.map((p) => (
            <Grid item xs={12} sm={6} md={4} lg={3} key={p.problem_id}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="subtitle1" noWrap gutterBottom>
                    {p.problem_title}
                  </Typography>
                  <Box sx={{ display: "flex", gap: 0.5, mb: 1, flexWrap: "wrap" }}>
                    <Chip
                      label={p.difficulty}
                      size="small"
                      sx={{
                        bgcolor:
                          DIFFICULTY_COLORS[p.difficulty] ??
                          "#9CA3AF",
                        color: "#fff",
                        fontWeight: 600,
                      }}
                    />
                    <Chip label={p.platform} size="small" variant="outlined" />
                  </Box>
                  <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mb: 1 }}>
                    {p.tags.slice(0, 4).map((t) => (
                      <Chip key={t} label={t} size="small" />
                    ))}
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    {p.reason}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="primary"
                    sx={{ mt: 1, display: "block" }}
                  >
                    推荐度: {p.priority}%
                  </Typography>
                </CardContent>
                <CardActions>
                  <Button size="small" endIcon={<LaunchIcon />}>
                    查看题目
                  </Button>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
