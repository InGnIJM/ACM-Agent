// ============================================================
// TeamDetail page — team member profile cards, compatibility
// scores, team strengths coverage radar.
// ============================================================

import { useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Avatar from "@mui/material/Avatar";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import useApi from "../hooks/useApi";
import * as matchingApi from "../services/matching";
import type { Team } from "../types/team";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

function stringToColor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00ffffff).toString(16).toUpperCase();
  return "#" + "00000".substring(0, 6 - c.length) + c;
}

export default function TeamDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const numericId = Number(id);

  const fetcher = useCallback(
    () => matchingApi.getTeam(numericId),
    [numericId],
  );

  const { data: team, loading, error } = useApi<Team>(fetcher, [numericId]);

  // Dummy strengths coverage radar data
  const coverageData = [
    { label: "图论", value: 85 },
    { label: "DP", value: 60 },
    { label: "贪心", value: 90 },
    { label: "数据结构", value: 75 },
    { label: "数学", value: 50 },
    { label: "字符串", value: 70 },
  ];

  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Skeleton variant="text" width={300} height={40} />
        <Skeleton variant="rectangular" height={200} sx={{ mt: 2 }} />
      </Box>
    );
  }

  if (error || !team) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{error ?? "队伍未找到"}</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate("/teams")}
        sx={{ mb: 2 }}
      >
        返回队伍列表
      </Button>

      {/* ---- header ---- */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 1 }}>
          <Typography variant="h4">{team.name}</Typography>
          <Chip
            label={
              team.status === "recruiting"
                ? "招募中"
                : team.status === "full"
                  ? "已满"
                  : "不活跃"
            }
            color={
              team.status === "recruiting"
                ? "success"
                : team.status === "full"
                  ? "warning"
                  : "default"
            }
          />
        </Box>
        {team.description && (
          <Typography variant="body1" color="text.secondary">
            {team.description}
          </Typography>
        )}
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 1 }}>
          {team.tags.map((t) => (
            <Chip key={t} label={t} size="small" />
          ))}
        </Box>
      </Paper>

      <Grid container spacing={3}>
        {/* ---- members ---- */}
        <Grid item xs={12} md={7}>
          <Typography variant="h6" gutterBottom>
            队伍成员 ({team.members.length}/{team.max_members})
          </Typography>
          <Grid container spacing={2}>
            {team.members.map((m) => (
              <Grid item xs={12} sm={6} key={m.user_id}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 1 }}>
                      <Avatar
                        sx={{ bgcolor: stringToColor(m.username), width: 48, height: 48 }}
                      >
                        {(m.nickname ?? m.username).charAt(0).toUpperCase()}
                      </Avatar>
                      <Box>
                        <Typography variant="subtitle1">
                          {m.nickname ?? m.username}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          @{m.username}
                        </Typography>
                      </Box>
                      <Chip
                        label={m.role === "leader" ? "队长" : "成员"}
                        size="small"
                        color={m.role === "leader" ? "primary" : "default"}
                        sx={{ ml: "auto" }}
                      />
                    </Box>
                    <Divider sx={{ my: 1 }} />
                    <Typography variant="body2" color="text.secondary">
                      加入时间: {new Date(m.joined_at).toLocaleDateString()}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Grid>

        {/* ---- strengths coverage ---- */}
        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              队伍技能覆盖
            </Typography>
            <ResponsiveContainer width="100%" height={280}>
              <RadarChart data={coverageData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="label" />
                <PolarRadiusAxis angle={30} domain={[0, 100]} />
                <Radar
                  name="覆盖率"
                  dataKey="value"
                  stroke="#1E40AF"
                  fill="#1E40AF"
                  fillOpacity={0.3}
                />
              </RadarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}
