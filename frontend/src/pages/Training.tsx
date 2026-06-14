// ============================================================
// Training page — current training plan: phase badge, weekly view,
// each day has problem cards with difficulty badges.
// ============================================================

import { useMemo, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import useApi from "../hooks/useApi";
import useAuth from "../hooks/useAuth";
import * as trainingApi from "../services/training";
import type { TrainingPlan } from "../types/training";

const PHASE_COLORS: Record<string, string> = {
  基础期: "#22C55E",
  强化期: "#3B82F6",
  冲刺期: "#EF4444",
};

export default function Training() {
  const { user } = useAuth();
  const userId = user?.id ?? 0;

  const planFetcher = useCallback(
    () => trainingApi.getPlan(userId),
    [userId],
  );

  const { data: plan, loading, error } = useApi<TrainingPlan>(planFetcher, [
    userId,
  ]);

  // Group tasks into weeks (7 days per week)
  const weeks = useMemo(() => {
    if (!plan?.tasks) return [];
    const result: (typeof plan.tasks)[] = [];
    for (let i = 0; i < plan.tasks.length; i += 7) {
      result.push(plan.tasks.slice(i, i + 7));
    }
    return result;
  }, [plan]);

  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Skeleton variant="text" width={260} height={40} />
        <Skeleton variant="rectangular" height={200} sx={{ mt: 2 }} />
      </Box>
    );
  }

  if (error || !plan) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info" action={<Button color="inherit" size="small">生成计划</Button>}>
          暂无训练计划，点击右侧按钮生成一个适合你的计划。
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
        <Typography variant="h4">{plan.name}</Typography>
        <Chip
          label={"进行中"}
          color="primary"
          size="small"
        />
      </Box>

      {plan.description && (
        <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
          {plan.description}
        </Typography>
      )}

      {weeks.map((weekTasks, weekIdx) => (
        <Paper key={weekIdx} sx={{ p: 2, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            第 {weekIdx + 1} 周
          </Typography>
          <Grid container spacing={2}>
            {weekTasks.map((task) => (
              <Grid item xs={12} sm={6} md={4} lg={12 / 7} key={task.day}>
                <Card variant="outlined" sx={{ height: "100%" }}>
                  <CardContent sx={{ p: 1.5 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      第 {task.day} 天
                    </Typography>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      {task.problem_count} 题
                    </Typography>
                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mb: 1 }}>
                      <Chip
                        label={`简 ${task.difficulty_distribution.easy}`}
                        size="small"
                        sx={{ bgcolor: "#22C55E", color: "#fff", fontSize: 11 }}
                      />
                      <Chip
                        label={`中 ${task.difficulty_distribution.medium}`}
                        size="small"
                        sx={{ bgcolor: "#F59E0B", color: "#fff", fontSize: 11 }}
                      />
                      <Chip
                        label={`难 ${task.difficulty_distribution.hard}`}
                        size="small"
                        sx={{ bgcolor: "#EF4444", color: "#fff", fontSize: 11 }}
                      />
                    </Box>
                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                      {task.topics.map((t) => (
                        <Chip key={t} label={t} size="small" variant="outlined" />
                      ))}
                    </Box>
                    {task.notes && (
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                        {task.notes}
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Paper>
      ))}
    </Box>
  );
}
