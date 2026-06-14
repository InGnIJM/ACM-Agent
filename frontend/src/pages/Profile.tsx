// ============================================================
// Profile page — 6-dimension skill overview, SkillRadar chart,
// strengths/weaknesses cards, AI summary, difficulty pie chart.
// ============================================================

import { useMemo, useCallback } from "react";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import useApi from "../hooks/useApi";
import useAuth from "../hooks/useAuth";
import * as profilesApi from "../services/profiles";
import type { Profile as ProfileData } from "../types/profile";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

export default function Profile() {
  const { user } = useAuth();
  const userId = user?.id;

  const fetcher = useCallback(
    () => userId ? profilesApi.getProfile(userId) : Promise.resolve(null),
    [userId],
  );

  const { data: profile, loading, error } = useApi<ProfileData | null>(fetcher, [userId]);

  if (!userId) return <Box sx={{ p: 3 }}><Alert severity="warning">请先登录</Alert></Box>;

  if (loading) return <Box sx={{ p: 3 }}><Skeleton variant="text" width={200} height={40} /><Skeleton variant="rectangular" height={300} sx={{ mt: 2 }} /></Box>;

  if (error || !profile) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>用户画像</Typography>
        <Alert severity="info" sx={{ mb: 2 }}>
          暂无画像数据。请在完成至少 10 道练习后生成画像。
        </Alert>
      </Box>
    );
  }

  if (!profile) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info">
          暂无分析数据，请先完成一些题目后再回来查看。
        </Alert>
      </Box>
    );
  }

  const s = profile.summary;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>用户画像</Typography>
      <Alert severity="info">画像功能将在用户完成练习后自动启用，敬请期待。</Alert>
    </Box>
  );
}
