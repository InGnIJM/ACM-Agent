// ============================================================
// Teams page — team list cards with member avatars and names.
// ============================================================

import { useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActions from "@mui/material/CardActions";
import Avatar from "@mui/material/Avatar";
import AvatarGroup from "@mui/material/AvatarGroup";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import useApi from "../hooks/useApi";
import * as matchingApi from "../services/matching";
import type { Team } from "../types/team";

function stringToColor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00ffffff).toString(16).toUpperCase();
  return "#" + "00000".substring(0, 6 - c.length) + c;
}

const STATUS_COLORS: Record<string, "success" | "warning" | "default"> = {
  recruiting: "success",
  full: "warning",
  inactive: "default",
};

const STATUS_LABELS: Record<string, string> = {
  recruiting: "招募中",
  full: "已满",
  inactive: "不活跃",
};

export default function Teams() {
  const navigate = useNavigate();

  const fetcher = useCallback(() => matchingApi.getTeams(), []);

  const { data: teams, loading, error } = useApi<Team[]>(fetcher, []);

  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Skeleton variant="text" width={200} height={40} />
        <Grid container spacing={2} sx={{ mt: 1 }}>
          {[1, 2, 3].map((n) => (
            <Grid item xs={12} sm={6} md={4} key={n}>
              <Skeleton variant="rectangular" height={160} />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h4">队伍</Typography>
        <Button variant="contained" onClick={() => navigate("/matching")}>
          寻找队友
        </Button>
      </Box>

      {!teams || teams.length === 0 ? (
        <Alert severity="info">暂无队伍，去匹配页面寻找队友创建队伍吧。</Alert>
      ) : (
        <Grid container spacing={2}>
          {teams.map((team) => (
            <Grid item xs={12} sm={6} md={4} key={team.id}>
              <Card variant="outlined">
                <CardContent>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 1 }}>
                    <Typography variant="h6" gutterBottom>
                      {team.name}
                    </Typography>
                    <Chip
                      label={STATUS_LABELS[team.status] ?? team.status}
                      size="small"
                      color={STATUS_COLORS[team.status] ?? "default"}
                    />
                  </Box>

                  {team.description && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      {team.description}
                    </Typography>
                  )}

                  {/* tags */}
                  <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mb: 1 }}>
                    {team.tags.map((t) => (
                      <Chip key={t} label={t} size="small" variant="outlined" />
                    ))}
                  </Box>

                  {/* members */}
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <AvatarGroup max={5}>
                      {team.members.map((m) => (
                        <Avatar
                          key={m.user_id}
                          alt={m.nickname ?? m.username}
                          sx={{ bgcolor: stringToColor(m.username), width: 32, height: 32, fontSize: 14 }}
                        >
                          {(m.nickname ?? m.username).charAt(0).toUpperCase()}
                        </Avatar>
                      ))}
                    </AvatarGroup>
                    <Typography variant="body2" color="text.secondary">
                      {team.members.length}/{team.max_members} 人
                    </Typography>
                  </Box>
                </CardContent>
                <CardActions>
                  <Button size="small" onClick={() => navigate(`/teams/${team.id}`)}>
                    查看详情
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
