// ============================================================
// Ranking page — ranking table (AC count, streak, rating),
// with tabs for daily / weekly / all-time.
// ============================================================

import { useState, useCallback, useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";

// ---- static mock data — replace with real API call in production ----
interface RankEntry {
  rank: number;
  username: string;
  nickname?: string;
  ac_count: number;
  streak: number;
  rating: number;
}

function generateMockData(): RankEntry[] {
  return Array.from({ length: 20 }, (_, i) => ({
    rank: i + 1,
    username: `user_${i + 1}`,
    nickname: `选手${i + 1}`,
    ac_count: Math.floor(Math.random() * 500) + 50,
    streak: Math.floor(Math.random() * 30) + 1,
    rating: Math.floor(Math.random() * 2000) + 800,
  }));
}

export default function Ranking() {
  const [tab, setTab] = useState(0);

  const data = useMemo(() => generateMockData(), []);

  const rankBadge = (rank: number) => {
    if (rank === 1)
      return (
        <Chip
          label={`#${rank}`}
          size="small"
          sx={{ bgcolor: "#FFD700", color: "#000", fontWeight: 700 }}
        />
      );
    if (rank === 2)
      return (
        <Chip
          label={`#${rank}`}
          size="small"
          sx={{ bgcolor: "#C0C0C0", color: "#000", fontWeight: 700 }}
        />
      );
    if (rank === 3)
      return (
        <Chip
          label={`#${rank}`}
          size="small"
          sx={{ bgcolor: "#CD7F32", color: "#fff", fontWeight: 700 }}
        />
      );
    return (
      <Typography variant="body2" color="text.secondary">
        #{rank}
      </Typography>
    );
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        排行榜
      </Typography>

      <Paper sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="每日" />
          <Tab label="每周" />
          <Tab label="全部" />
        </Tabs>
      </Paper>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell width={70}>排名</TableCell>
              <TableCell>用户</TableCell>
              <TableCell width={100}>AC 数</TableCell>
              <TableCell width={100}>连续天数</TableCell>
              <TableCell width={100}>Rating</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((entry) => (
              <TableRow key={entry.rank}>
                <TableCell>{rankBadge(entry.rank)}</TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}>
                    {entry.nickname ?? entry.username}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    @{entry.username}
                  </Typography>
                </TableCell>
                <TableCell>{entry.ac_count}</TableCell>
                <TableCell>{entry.streak} 天</TableCell>
                <TableCell>{entry.rating}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
