import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import "katex/dist/katex.min.css";
import "./markdown.css";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import InputOutlinedIcon from "@mui/icons-material/InputOutlined";
import OutputOutlinedIcon from "@mui/icons-material/OutputOutlined";
import TipsAndUpdatesOutlinedIcon from "@mui/icons-material/TipsAndUpdatesOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import LightbulbOutlinedIcon from "@mui/icons-material/LightbulbOutlined";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import CheckIcon from "@mui/icons-material/Check";
import type { Components } from "react-markdown";

/* ──────────────────────────────────────────────────
 *  Shared helpers
 * ────────────────────────────────────────────────── */

/** Map header text to Material Symbols icon */
function headerIcon(text: string) {
  const t = String(text).trim();
  if (t.includes("背景")) return <InfoOutlinedIcon fontSize="inherit" sx={{ mr: 0.5, verticalAlign: "middle" }} />;
  if (t.includes("描述")) return <DescriptionOutlinedIcon fontSize="inherit" sx={{ mr: 0.5, verticalAlign: "middle" }} />;
  if (t.includes("输入")) return <InputOutlinedIcon fontSize="inherit" sx={{ mr: 0.5, verticalAlign: "middle" }} />;
  if (t.includes("输出")) return <OutputOutlinedIcon fontSize="inherit" sx={{ mr: 0.5, verticalAlign: "middle" }} />;
  if (t.includes("提示")) return <TipsAndUpdatesOutlinedIcon fontSize="inherit" sx={{ mr: 0.5, verticalAlign: "middle" }} />;
  if (t.includes("解释")) return <LightbulbOutlinedIcon fontSize="inherit" sx={{ mr: 0.5, verticalAlign: "middle" }} />;
  if (t.includes("数据范围")) return <BarChartOutlinedIcon fontSize="inherit" sx={{ mr: 0.5, verticalAlign: "middle" }} />;
  return null;
}

/** Shared colour palette — Luogu-inspired: light surface, high-contrast text */
const COLORS = {
  blockCodeBg: "#f8f9fa",
  blockCodeFg: "#1e293b",
  blockCodeBorder: "#e5e7eb",
  blockquoteBorder: "primary.light",
  blockquoteBg: "grey.100",
  tableBorder: "grey.300",
  tableHeaderBg: "grey.100",
} as const;

/* ──────────────────────────────────────────────────
 *  CodeBlock with copy button
 * ────────────────────────────────────────────────── */

/** Extract plain text from React children for clipboard copy. */
function extractText(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(extractText).join("");
  if (children && typeof children === "object" && "props" in children) {
    return extractText((children as any).props?.children ?? "");
  }
  return "";
}

/**
 * Block-level code with copy-to-clipboard button.
 *
 * IMPORTANT: used as the `pre` component override in react-markdown,
 * NOT the `code` component.  react-markdown passes the already-rendered
 * `<code>` element as children, so we just wrap it in our own `<pre>`
 * to avoid invalid `<code><div>…</div></code>` DOM nesting.
 *
 * Structure: <Box position="relative"> (for copy button positioning)
 *            ├── <Button> (copy button)
 *            └── <pre> (code container with styling)
 */
/**
 * Enhanced code block with copy button and future extensibility hooks.
 *
 * Structure for easy extension:
 * - Outer container: <Box position="relative"> (holds button + pre container)
 * - Copy button: <IconButton> with copy functionality
 * - Inner container: <Box> (future: can hold additional features like line numbers)
 * - Code wrapper: <pre> (actual code styling and content)
 *
 * Future extensions can be added to the pre container without breaking
 * existing copy functionality.
 */
function CodeBlock({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const text = extractText(children);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Box sx={{ position: "relative", maxWidth: "100%", my: 1.5 }}>
      <Tooltip title={copied ? "已复制" : "复制代码"} arrow>
        <IconButton
          size="small"
          onClick={handleCopy}
          sx={{
            position: "absolute",
            top: 6,
            right: 6,
            zIndex: 1,
            color: copied ? "success.main" : "grey.500",
            bgcolor: "rgba(248,250,252,0.75)",
            "&:hover": {
              bgcolor: "rgba(226,232,240,0.85)",
              color: "grey.700",
            },
            transition: "color 0.2s",
          }}
        >
          {copied ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
      {/*
        Future extensibility container: This box can hold additional features
        like line numbers, syntax highlighting controls, or other utilities
        without affecting the core copy functionality.
      */}
      <Box sx={{ position: "relative" }}>
        <pre
          style={{
            backgroundColor: COLORS.blockCodeBg,
            color: COLORS.blockCodeFg,
            padding: 16,
            borderRadius: 8,
            border: `1px solid ${COLORS.blockCodeBorder}`,
            overflowX: "auto",
            fontSize: "0.875rem",
            lineHeight: 1.7,
            maxWidth: "100%",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}
        >
          {children}
        </pre>
      </Box>
    </Box>
  );
}

/* ──────────────────────────────────────────────────
 *  react-markdown components
 * ────────────────────────────────────────────────── */

const components: Partial<Components> = {
  h1: ({ children }) => <Typography variant="h4" gutterBottom>{children}</Typography>,
  h2: ({ children }) => (
    <Typography variant="h5" gutterBottom sx={{ mt: 2, fontWeight: 700, display: "flex", alignItems: "center" }}>
      {headerIcon(String(children))}
      {children}
    </Typography>
  ),
  h3: ({ children }) => (
    <Typography variant="h6" gutterBottom sx={{ fontWeight: 600, mt: 1.5, display: "flex", alignItems: "center" }}>
      {headerIcon(String(children))}
      {children}
    </Typography>
  ),

  /* ── Paragraph ─────────────────────────────── */
  p: ({ children }) => {
    // Detect CF statement-footnote paragraphs: they start with a rendered
    // footnote marker (∗ / †) from $^{\ast} / $^{\dagger}$.  Render those at
    // reduced size + muted colour (matching CF's .statement-footnote).
    const text = extractText(children);
    const isFootnote = /^[∗††‡]/.test(text.trim());
    return (
      <Typography
        variant={isFootnote ? "caption" : "body1"}
        component="p"
        data-footnote={isFootnote ? "true" : undefined}
        sx={{
          mb: 2,
          lineHeight: isFootnote ? 1.6 : 2,
          color: isFootnote ? "text.secondary" : undefined,
          overflowWrap: "break-word",
          wordBreak: "break-word",
        }}
      >
        {children}
      </Typography>
    );
  },

  /* ── Lists ─────────────────────────────────── */
  ul: ({ children }) => (
    <Box component="ul" sx={{ pl: 3, mb: 2, mt: 0 }}>
      {children}
    </Box>
  ),
  ol: ({ children }) => (
    <Box component="ol" sx={{ pl: 3, mb: 2, mt: 0 }}>
      {children}
    </Box>
  ),
  li: ({ children }) => (
    <Box component="li" sx={{ mb: 0.5, lineHeight: 1.8, overflowWrap: "break-word", wordBreak: "break-word" }}>
      <Typography variant="body1" component="span">{children}</Typography>
    </Box>
  ),

  /* ── Blockquote ────────────────────────────── */
  blockquote: ({ children }) => (
    <Box
      sx={{
        borderLeft: 4,
        borderColor: COLORS.blockquoteBorder,
        pl: 2,
        py: 0.5,
        my: 2,
        bgcolor: COLORS.blockquoteBg,
        borderRadius: "0 4px 4px 0",
        overflowWrap: "break-word",
      }}
    >
      {children}
    </Box>
  ),

  /* ── Images ────────────────────────────────── */
  img: ({ src, alt }: any) => (
    <Box sx={{ my: 2, maxWidth: "100%", overflow: "hidden" }}>
      <img
        src={src}
        alt={alt || ""}
        style={{ maxWidth: "100%", maxHeight: 400, height: "auto", width: "auto", borderRadius: 8, objectFit: "contain" }}
        loading="lazy"
      />
    </Box>
  ),

  /* ── Code: structure only ────────────────────────────────
   * Styling comes from markdown.css via tag layering: block code is inside
   * <pre> (handled by CodeBlock above), inline code is matched by
   * `:not(pre) > code`.  We deliberately do NOT branch on `className` here:
   * language-less fenced code has no className and would otherwise be
   * misclassified as inline code, whose padding only applies to the first
   * line of a multi-line element — producing a phantom first-line indent
   * (regression: Codeforces 2236F2 sample input).  We still forward
   * `className` so language-hinted blocks keep their `language-xxx` class. */
  code: ({ className, children }: any) => <code className={className}>{children}</code>,

  /* ── Pre: block-level code with copy button ── */
  pre: ({ children }: any) => <CodeBlock>{children}</CodeBlock>,

  /* ── Tables ────────────────────────────────── */
  table: ({ children }) => (
    <Box sx={{ overflowX: "auto", my: 2, maxWidth: "100%" }}>
      <Box component="table" sx={{ borderCollapse: "collapse", width: "100%", fontSize: "0.95rem" }}>
        {children}
      </Box>
    </Box>
  ),
  th: ({ children }) => (
    <Box
      component="th"
      sx={{
        border: "1px solid",
        borderColor: COLORS.tableBorder,
        px: 2,
        py: 1,
        bgcolor: COLORS.tableHeaderBg,
        fontWeight: 700,
        textAlign: "left",
      }}
    >
      {children}
    </Box>
  ),
  td: ({ children }) => (
    <Box component="td" sx={{ border: "1px solid", borderColor: COLORS.tableBorder, px: 2, py: 1 }}>
      {children}
    </Box>
  ),

  /* ── Links ──────────────────────────────────── */
  a: ({ href, children }: any) => (
    <Link href={href} target="_blank" rel="noopener noreferrer" underline="hover" sx={{ wordBreak: "break-all" }}>
      {children}
    </Link>
  ),

  /* ── Inline formatting ──────────────────────── */
  strong: ({ children }) => <Box component="strong" sx={{ fontWeight: 700 }}>{children}</Box>,
  em: ({ children }) => <Box component="em" sx={{ fontStyle: "italic" }}>{children}</Box>,
  hr: () => <Box component="hr" sx={{ my: 2, borderColor: "grey.300" }} />,
};

/* ──────────────────────────────────────────────────
 *  Platform-specific preprocessing
 * ────────────────────────────────────────────────── */

/**
 * Strip zero-width characters that break dedup clusters.
 * U+200B (ZWSP), U+200C (ZWNJ), U+200D (ZWJ), U+FEFF (BOM).
 */
function stripZeroWidthChars(content: string): string {
  return content.replace(/[​‌‍﻿]/g, "");
}

/**
 * Deduplicate MathJax triplication (shared by CF + NowCoder).
 *
 * OJ pages render each math symbol 3 ways (plain-text preview, LaTeX source,
 * rendered nobr), producing patterns like:
 *   p\ni\n\np\ni\n\np_i   (multi-line)  → keep only "p_i"
 *   n\nn\nn               (single-char)  → keep one "n"
 *
 * Strategy: within runs of consecutive non-CJK short lines separated by blank
 * lines, keep only the longest / most LaTeX-rich variant.
 * Uses negation (no CJK chars) instead of ASCII-whitelist so Unicode math
 * symbols and zero-width chars are included in clusters and deduplicated away.
 */
function dedupMathJax(content: string): string {
  // ── Pre-pass: merge blank-line-separated math islands ──────────────────
  // CF crawler produces "\n\n1\n\n≤\n\nx\n\n1 \le x\n\n." — each symbol
  // on its own line.  Without this step blank lines break the cluster
  // algorithm and every fragment becomes a cluster of size 1.
  {
    const lines = content.split("\n");
    const merged: string[] = [];
    let i = 0;
    // Track fenced code blocks (``` / ~~~) so their contents are preserved
    // verbatim and never misclassified as MathJax triplication islands.
    let inCodeBlock = false;

    const isMathFragment = (s: string): boolean => {
      if (s === "") return false;
      if (s.length > 80) return false;
      if (s.startsWith("[") || s.startsWith("##") || s.startsWith("【")) return false;
      if (/[一-鿿]/.test(s)) return false;
      if (s.length <= 3) {
        return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞​''′`]+$/.test(s);
      }
      if (!/[_^|\\{}×∙∣≤≥±∞]/.test(s)) return false;
      return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞​''′`]+$/.test(s);
    };

    while (i < lines.length) {
      const t = lines[i].trim();
      // Fenced code blocks (``` or ~~~) are preserved verbatim — their
      // contents must NOT be misclassified as MathJax triplication islands.
      // Regression: Codeforces 2236B sample I/O was crushed because short
      // numeric lines (5, 4 2, 111, …) and ``` fences inside code blocks
      // all matched isMathFragment, so multi-line samples collapsed to one
      // line and the closing fences were swallowed.
      if (t.startsWith("```") || t.startsWith("~~~")) {
        inCodeBlock = !inCodeBlock;
        merged.push(lines[i]);
        i++;
        continue;
      }
      if (inCodeBlock) {
        merged.push(lines[i]);
        i++;
        continue;
      }
      if (t === "" || !isMathFragment(t)) {
        merged.push(lines[i]);
        i++;
        continue;
      }

      // Collect a math island — skip blank lines between fragments
      const island: string[] = [lines[i]];
      i++;
      while (i < lines.length) {
        const s = lines[i].trim();
        // Never let an island cross a code fence.
        if (s.startsWith("```") || s.startsWith("~~~")) break;
        if (s === "") {
          let peek = i + 1;
          while (peek < lines.length && lines[peek].trim() === "") peek++;
          if (peek < lines.length && isMathFragment(lines[peek].trim())) {
            i++; // blank between math fragments → skip
            continue;
          }
          break; // blank not between math → end island
        }
        if (isMathFragment(s)) {
          island.push(lines[i]);
          i++;
        } else {
          break;
        }
      }

      if (island.length >= 3) {
        const best = island.reduce((a, b) =>
          (b.trim().length > a.trim().length || /[_^|\\{}]/.test(b)) ? b : a,
          island[0]
        );
        merged.push(best.trim());
      } else {
        merged.push(...island.map((l) => l.trim()));
      }
    }

    content = merged.join("\n");
  }

  return content;
}

/** Convert Luogu-style [section] markers → ## H2 headers. Shared by all platforms. */
function preprocessSections(content: string): string {
  return content
    .replace(/^\[背景\]/gm, "## 背景\n")
    .replace(/^\[描述\]/gm, "## 题目描述\n")
    .replace(/^\[输入\]/gm, "## 输入格式\n")
    .replace(/^\[输出\]/gm, "## 输出格式\n")
    .replace(/^\[提示\]/gm, "## 提示\n")
    .replace(/^\[样例\]/gm, "## 样例\n")
    .replace(/^\[注\]/gm, "## 注\n")
    .replace(/^\[数据范围\]/gm, "## 数据范围\n")
    // Elevate sample I/O labels to ### sub-headings with icon + hierarchy
    .replace(/^(输入|输出|解释)\s+(#\d+)\s*$/gm, "\n### $1 $2\n");
}

/**
 * LeetCode: stripped-HTML plain text.
 * - Detect "示例 N：" / "Example N:" → ### sub-headings.
 * - Detect "提示：" / "Constraints:" → ### sub-headings.
 * - Bold "输入：" / "Output:" labels so they stand out.
 */
function preprocessLeetcode(content: string): string {
  let c = preprocessSections(content);
  // Example headers (both languages)
  c = c.replace(/^(示例\s*\d+)[：:]/gim, "### $1：");
  c = c.replace(/^(Example\s+\d+)[：:]/gim, "### $1：");
  // Section-like labels
  c = c.replace(/^(提示|进阶|注意)[：:]/gim, "### $1：");
  c = c.replace(/^(Constraints|Follow-up|Note)[：:]/gim, "### $1：");
  // Bold Input / Output / Explanation labels
  c = c.replace(/^(输入|输出|解释)\s*(\d*)[：:]/gim, "**$1$2：**");
  c = c.replace(/^(Input|Output|Explanation)\s*(\d*)[：:]/gim, "**$1$2：**");
  return c;
}

/**
 * Codeforces: aggressive MathJax triplication cleanup.
 *
 * CF pages render math 3 ways (plain text, LaTeX source, rendered).
 * This produces patterns like "p\ni\n\np\ni\n\np_i" — 3 copies spread
 * across lines.  We use a multi-pass dedup:
 * 1. Collapse single-char clusters (p\n\ni → pi)
 * 2. Remove plain-text duplicates before LaTeX variants
 * 3. Final whitespace normalization
 */
function preprocessCodeforces(content: string): string {
  let c = preprocessSections(content);
  c = dedupMathJax(c);
  // Ensure blank line after ## headings so markdown parses correctly
  c = c.replace(/^(## .+)$/gm, "$1\n");
  // Isolate $$...$$ display math onto its own line so remark-math renders it
  // as a centered display block.  Without surrounding blank lines,
  // react-markdown treats $$...$$ as inline math glued to adjacent text.
  // Regression: 2236G's large formula rendered inline (no new line, no center).
  // Done before the bare-token wrap below so the already-$$-wrapped block is
  // protected as one span.
  c = c.replace(/\$\$([\s\S]+?)\$\$/g, (_m, content) => `\n\n$$${content}$$\n\n`);
  // Wrap bare LaTeX tokens in $…$ for KaTeX rendering (defence-in-depth —
  // old DB rows may carry \commands outside $...$ because the crawler's
  // historical $$-merge regex stripped display fences; the backend is now
  // fixed, but this rescues already-stored data).  Only wraps tokens NOT
  // already inside $...$ / $$...$$ and NOT inside ``` code fences.
  // IMPORTANT: protect entire math spans first (display $$...$$ before
  // inline $...$) with placeholders so the bare-token wrap never reaches
  // INTO a math span and splits it (regression: a $$...$$ display block
  // had its inner \oplus pulled out and re-wrapped, shattering the block).
  {
    const _lines = c.split("\n");
    const _out: string[] = [];
    let _inFence = false;
    for (const _line of _lines) {
      const _t = _line.trim();
      if (_t.startsWith("```") || _t.startsWith("~~~")) {
        _inFence = !_inFence;
        _out.push(_line);
        continue;
      }
      if (_inFence) { _out.push(_line); continue; }
      const _spans: string[] = [];
      let _p = _line.replace(/\$\$[^$]*\$\$|\$[^$]*\$/g, (m) => {
        const idx = _spans.length;
        _spans.push(m);
        return `\x00${idx}\x00`;
      });
      // Wrap each bare \command (with optional {...} arg) in its own $...$
      _p = _p.replace(/\\[a-zA-Z]+(?:\{[^}]*\})?/g, (m) => `$${m}$`);
      _out.push(_p.replace(/\x00(\d+)\x00/g, (_m, idx) => _spans[Number(idx)]));
    }
    c = _out.join("\n");
  }
  // ── Paragraph recovery ────────────────────────────────────
  // CF text extracted from <p> elements lacks blank lines between
  // paragraphs (BS4's get_text("\n") produces only single \n
  // between adjacent <p> tags).  Without blank lines, markdown
  // renders them as one giant blob.  Insert blank lines at
  // ".!?"-ending → uppercase-starting boundaries, skipping code
  // blocks and headings.
  {
    const lines = c.split("\n");
    const out: string[] = [];
    let inFence = false;
    for (let i = 0; i < lines.length; i++) {
      const raw = lines[i];
      const t = raw.trim();
      if (t.startsWith("```") || t.startsWith("~~~")) {
        inFence = !inFence;
        out.push(raw);
        continue;
      }
      if (inFence) { out.push(raw); continue; }
      if (!t || t.startsWith("#")) { out.push(raw); continue; }
      if (i > 0 && out.length > 0) {
        const prev = out[out.length - 1].trim();
        if (prev && !prev.startsWith("#") && !prev.startsWith("*") &&
            /[.!?]$/.test(prev) && /^[A-Z]/.test(t)) {
          out.push("");
        }
      }
      out.push(raw);
    }
    c = out.join("\n");
  }
  // ── Footnote separation ─────────────────────────────────────
  // CF statement-footnotes render as small standalone lines.  Their
  // DEFINITIONS (e.g. "ideal.$^{\ast}lcm$ — least common multiple.")
  // appear glued to the preceding paragraph.  Break them onto their own
  // paragraph — but ONLY when preceded by a sentence-ending '.', so we
  // don't also break an inline footnote REFERENCE like "different$^{\dagger}$
  // arrays" (which would orphan the marker into its own footnote-styled
  // paragraph and shrink the body text).
  c = c.replace(/(?<=\.)\$\^\{\\(?:ast|dagger)\}/g, "\n\n$&");
  c = c.replace(/\n{3,}/g, "\n\n").trim();
  return c;
}

/**
 * NowCoder preprocessor — section markers + MathJax triplication dedup.
 *
 * NowCoder content has severe MathJax triplication where each math symbol
 * appears 3 ways (plain text, LaTeX source, rendered) separated by zero-width
 * spaces (U+200B).  Without proper cleanup, leftover "=" lines can trigger
 * Setext headings in markdown, turning paragraphs into <h1>.
 *
 * Pipeline:
 * 1. Strip zero-width chars so dedup clusters coalesce correctly.
 * 2. Dedup triplicated math fragments (plain-text / LaTeX / rendered).
 * 3. Strip leftover \\hspace / \\bullet artifacts.
 * 4. Escape standalone = or - lines so they don't become Setext underlines.
 * 5. Normalise whitespace around ## headings.
 */
function preprocessNowcoder(content: string): string {
  let c = preprocessSections(content);
  c = stripZeroWidthChars(c);
  // Normalise smart quotes and font glyph artifacts to ASCII — these
  // are KaTeX triplication remnants that confuse dedup and rendering.
  c = c.replace(/['']/g, "'");
  // NOTE: do NOT replace backtick (`) with apostrophe — the backend
  // wraps sample I/O in ``` code fences whose backticks would be
  // destroyed, and dedupMathJax would then misclassify the resulting
  // '''…data…''' clusters as MathJax triplication islands, collapsing
  // them and losing the input data entirely (regression: NowCoder 318732).
  c = c.replace(/′/g, "'");
  c = dedupMathJax(c);
  // Strip leftover LaTeX formatting artifacts (anywhere in text, not just line-start)
  c = c.replace(/\\[hv]space\{[^}]*\}/g, "");
  c = c.replace(/\\bullet/g, "∙");
  // Strip LaTeX spacing commands that may leak outside $…$ delimiters
  c = c.replace(/\\,/g, "");
  c = c.replace(/\\!/g, "");
  c = c.replace(/\\;/g, "");
  c = c.replace(/\\:/g, "");
  // Clean up empty math delimiters (leftover from stripping commands between $...$)
  c = c.replace(/\$\$/g, "");
  c = c.replace(/\$ \$/g, "");
  // Replace common LaTeX commands with Unicode (defence-in-depth)
  c = c.replace(/\\leqq?\b/g, "≤");
  c = c.replace(/\\geqq?\b/g, "≥");
  c = c.replace(/\\times\b/g, "×");
  c = c.replace(/\\cdot\b/g, "·");
  c = c.replace(/\\ldots\b/g, "...");
  c = c.replace(/\\cdots\b/g, "...");
  c = c.replace(/\\frac\b/g, "");
  // Safety: escape standalone = or - lines to prevent accidental Setext headings
  c = c.replace(/^([=\-]+)\s*$/gm, "\\$1");
  // Ensure blank line after ## headings
  c = c.replace(/^(## .+)$/gm, "$1\n");
  c = c.replace(/\n{3,}/g, "\n\n").trim();
  return c;
}

/* ──────────────────────────────────────────────────
 *  Dispatcher
 * ────────────────────────────────────────────────── */

function preprocessContent(content: string, platform?: string): string {
  switch (platform?.toLowerCase()) {
    case "leetcode":
      return preprocessLeetcode(content);
    case "codeforces":
      return preprocessCodeforces(content);
    case "nowcoder":
      return preprocessNowcoder(content);
    default:
      // Luogu, atcoder, unknown — standard section rendering
      return preprocessSections(content);
  }
}

/* ──────────────────────────────────────────────────
 *  Exported component
 * ────────────────────────────────────────────────── */

/* ── Exports for testing (tree-shakeable) ──────── */
export {
  stripZeroWidthChars,
  dedupMathJax,
  preprocessSections,
  preprocessLeetcode,
  preprocessCodeforces,
  preprocessNowcoder,
  preprocessContent,
};

/* ────────────────────────────────────────────────── */

interface MarkdownProps {
  content: string;
  sourcePlatform?: string;
}

export function Markdown({ content, sourcePlatform }: MarkdownProps) {
  if (!content) return <Typography color="text.secondary">暂无内容</Typography>;
  const processed = preprocessContent(content, sourcePlatform);
  return (
    <Box sx={{ minWidth: 0, overflow: "hidden", wordBreak: "break-word", fontSize: "1rem" }} className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]} components={components}>
        {processed}
      </ReactMarkdown>
    </Box>
  );
}
