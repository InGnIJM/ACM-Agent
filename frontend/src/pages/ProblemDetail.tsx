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

interface ApiSolution {
  id: string;
  author?: string;
  content: string;
  solutionIndex: number;
  createdAt: string;
}

/** @deprecated Use `Problem` from `../types/problem` instead (matches backend Prisma schema). */
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
  solutions?: ApiSolution[];
}

const DIFF_RANGES = [
  { min: 0, max: 999, label: "入门", color: "#22C55E" },
  { min: 1000, max: 1699, label: "普及", color: "#3B82F6" },
  { min: 1700, max: 2399, label: "提高", color: "#F97316" },
  { min: 2400, max: 3500, label: "省选/NOI", color: "#EF4444" },
];

/** Platform-specific config for community solution empty-state hints. */
const PLATFORM_SOLUTION_HINTS: Record<string, { name: string; solutionUrl: (sid: string) => string }> = {
  luogu: { name: "洛谷", solutionUrl: (sid) => `https://www.luogu.com.cn/problem/solution/${sid}` },
  codeforces: { name: "Codeforces", solutionUrl: (sid) => `https://codeforces.com/blog/entries/?tags=${sid}` },
  leetcode: { name: "LeetCode", solutionUrl: (sid) => `https://leetcode.cn/problems/${sid}/solution/` },
  nowcoder: { name: "NowCoder", solutionUrl: (sid) => `https://ac.nowcoder.com/acm/problem/discuss/${sid}` },
  atcoder: { name: "AtCoder", solutionUrl: (sid) => `https://atcoder.jp/contests/${sid}/editorial` },
};

function PlatformSolutionHint({ platform, sourceId }: { platform: string; sourceId: string }) {
  const cfg = PLATFORM_SOLUTION_HINTS[platform?.toLowerCase()];
  if (!cfg) {
    return <span>暂无社区题解。请在爬虫管理页面重新爬取题目即可获取题解。</span>;
  }
  return (
    <span>
      暂无社区题解。请先在爬虫管理页面
      <Link href="/admin/crawler" sx={{ mx: 0.5 }}>登录 {cfg.name}</Link>
      ，然后重新爬取题目即可获取题解。也可以直接前往
      <Link href={cfg.solutionUrl(sourceId)} target="_blank" sx={{ mx: 0.5 }}>
        {cfg.name}题解页面
      </Link>
      查看。
    </span>
  );
}

function diffLabel(v: number): string {
  for (const r of DIFF_RANGES) {
    if (v >= r.min && v <= r.max) return r.label;
  }
  return "未知";
}

function diffColor(v: number): string {
  for (const r of DIFF_RANGES) {
    if (v >= r.min && v <= r.max) return r.color;
  }
  return "#9CA3AF";
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
            sx={{ bgcolor: diffColor(problem.difficultyNormalized), color: "#fff", fontWeight: 600 }}
          />
          <Link href={problem.sourceUrl ?? (() => { const p = problem.sourcePlatform; const id = problem.sourceId; if (p === 'codeforces') return `https://codeforces.com/problemset/problem/${id}`; if (p === 'leetcode') return `https://leetcode.com/problems/${id}/`; if (p === 'nowcoder') return `https://ac.nowcoder.com/acm/problem/${id}`; if (p === 'atcoder') return `https://atcoder.jp/contests/${id}/tasks/${id}`; return `https://www.luogu.com.cn/problem/${id}`; })()} target="_blank" underline="none">
            <Chip icon={<OpenInNewIcon />} label="原题链接" size="small" clickable color="primary" variant="outlined" />
          </Link>
        </Box>

        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <Chip label={`平台: ${problem.sourcePlatform}`} size="small" variant="outlined" />
          <Chip label={`题号: ${problem.sourceId}`} size="small" variant="outlined" />
          <Chip label={`难度: ${diffLabel(problem.difficultyNormalized)} (${problem.difficultyNormalized})`} size="small" variant="outlined" />
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
        <Paper sx={{ p: 3, overflow: "hidden" }}>
          <Box className="markdown-body">
          <Markdown content={problem.fullContent ?? "暂无题面数据"} sourcePlatform={problem.sourcePlatform} />
        </Box>
        </Paper>
      )}

      {/* Tab: Solutions */}
      {tab === 1 && (
        <Paper sx={{ p: 3, overflow: "hidden" }}>
          {/* Solution Summary */}
          <Typography variant="h6" gutterBottom>题解总结</Typography>
          <Box className="markdown-body">
          <Markdown content={problem.solutionSummary ?? "暂无题解总结（配置 DeepSeek API Key 后可获得 AI 生成的题解总结）"} sourcePlatform={problem.sourcePlatform} />
        </Box>

          <Divider sx={{ my: 3 }} />

          {/* Solutions List */}
          <Typography variant="h6" gutterBottom>社区题解 ({problem.solutions?.length ?? 0} 篇)</Typography>
          {problem.solutions && problem.solutions.length > 0 ? (
            problem.solutions.map((sol, idx) => (
              <Accordion key={sol.id}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography fontWeight={600}>
                    #{idx + 1} {sol.author ? `— ${sol.author}` : ''}
                  </Typography>
                </AccordionSummary>
                <AccordionDetails sx={{ overflow: "hidden" }}>
                  <Box className="markdown-body">
                    <Markdown content={sol.content} sourcePlatform={problem.sourcePlatform} />
                  </Box>
                </AccordionDetails>
              </Accordion>
            ))
          ) : (
            <Alert severity="info">
              <PlatformSolutionHint platform={problem.sourcePlatform} sourceId={problem.sourceId} />
            </Alert>
          )}
        </Paper>
      )}
    </Box>
  );
}
