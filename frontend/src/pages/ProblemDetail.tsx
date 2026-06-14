import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Link from "@mui/material/Link";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import useApi from "../hooks/useApi";
import * as problemsApi from "../services/problems";
import { Markdown } from "../components/common/Markdown";

interface ApiProblem {
  id: string;
  title: string;
  sourcePlatform: string;
  sourceId: string;
  sourceUrl: string;
  difficultyRaw: string;
  difficultyNormalized: number;
  tagsPlatform: number[];
  fullContent?: string;
  solutionSummary?: string;
}

const DIFF_COLORS: Record<number, string> = { 1: "#22C55E", 2: "#22C55E", 3: "#4ADE80", 4: "#F59E0B", 5: "#F59E0B", 6: "#F97316", 7: "#F97316", 8: "#EF4444", 9: "#EF4444", 10: "#DC2626" };

function diffLabel(v: number): string {
  if (v <= 2) return "入门";
  if (v <= 4) return "普及";
  if (v <= 6) return "提高";
  if (v <= 8) return "省选";
  return "NOI";
}

export default function ProblemDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState(0);

  const fetcher = useCallback(() => problemsApi.getProblem(id!), [id]);
  const { data: problem, loading, error } = useApi<ApiProblem>(fetcher, [id]);

  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Skeleton variant="text" width={300} height={40} />
        <Skeleton variant="rectangular" height={200} sx={{ mt: 2 }} />
      </Box>
    );
  }

  if (error || !problem) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{String(error ?? "题目未找到")}</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/problems")} sx={{ mb: 2 }}>
        返回题库
      </Button>

      {/* Header */}
      <Paper sx={{ p: 3, mb: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2, flexWrap: "wrap" }}>
          <Typography variant="h4">{problem.title}</Typography>
          <Chip
            label={diffLabel(problem.difficultyNormalized)}
            sx={{ bgcolor: DIFF_COLORS[Math.round(problem.difficultyNormalized)] ?? "#9CA3AF", color: "#fff", fontWeight: 600 }}
          />
          <Link href={problem.sourceUrl ?? `https://www.luogu.com.cn/problem/${problem.sourceId}`} target="_blank" underline="none">
            <Chip icon={<OpenInNewIcon />} label="原题链接" size="small" clickable color="primary" variant="outlined" />
          </Link>
        </Box>

        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <Chip label={`平台: ${problem.sourcePlatform}`} size="small" variant="outlined" />
          <Chip label={`题号: ${problem.sourceId}`} size="small" variant="outlined" />
          <Chip label={`难度: ${diffLabel(problem.difficultyNormalized)} (${problem.difficultyNormalized}/10)`} size="small" variant="outlined" />
        </Box>
      </Paper>

      {/* Tabs */}
      <Paper sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="题目描述" />
          <Tab label="题解" />
        </Tabs>
      </Paper>

      {/* Tab: Description */}
      {tab === 0 && (
        <Paper sx={{ p: 3 }}>
          <Markdown content={problem.fullContent ?? "暂无题面数据"} />
        </Paper>
      )}

      {/* Tab: Solutions */}
      {tab === 1 && (
        <Paper sx={{ p: 3 }}>
          {/* Solution Summary */}
          <Typography variant="h6" gutterBottom>题解总结</Typography>
          <Markdown content={problem.solutionSummary ?? "暂无题解总结"} />

          <Divider sx={{ my: 3 }} />

          {/* Solutions List */}
          <Typography variant="h6" gutterBottom>题解列表</Typography>
          <Alert severity="info" sx={{ mt: 1 }}>
            题解正在从各平台爬取中，请稍后查看。也可以直接前往
            <Link href={`https://www.luogu.com.cn/problem/solution/${problem.sourceId}`} target="_blank" sx={{ mx: 0.5 }}>
              洛谷题解页面
            </Link>
            查看。
          </Alert>
        </Paper>
      )}
    </Box>
  );
}
