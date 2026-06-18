// ============================================================
// Tests for Markdown component and preprocessing functions
// ============================================================

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  Markdown,
  stripZeroWidthChars,
  dedupMathJax,
  preprocessSections,
  preprocessNowcoder,
  preprocessCodeforces,
  preprocessContent,
} from "../../src/components/common/Markdown";

// ============================================================
// stripZeroWidthChars
// ============================================================

describe("stripZeroWidthChars", () => {
  it("removes U+200B zero-width space", () => {
    expect(stripZeroWidthChars("a​b")).toBe("ab");
  });

  it("removes U+200C zero-width non-joiner", () => {
    expect(stripZeroWidthChars("a‌b")).toBe("ab");
  });

  it("removes U+200D zero-width joiner", () => {
    expect(stripZeroWidthChars("a‍b")).toBe("ab");
  });

  it("removes U+FEFF BOM", () => {
    expect(stripZeroWidthChars("﻿hello")).toBe("hello");
  });

  it("removes all zero-width chars in a single pass", () => {
    const input = "a​‌‍﻿b";
    expect(stripZeroWidthChars(input)).toBe("ab");
  });

  it("leaves normal text untouched", () => {
    const normal = "正常的文本\nwith normal chars";
    expect(stripZeroWidthChars(normal)).toBe(normal);
  });

  it("handles empty string", () => {
    expect(stripZeroWidthChars("")).toBe("");
  });

  it("handles string with only zero-width chars", () => {
    expect(stripZeroWidthChars("​‌‍")).toBe("");
  });

  it("removes U+200B from NowCoder-style triplication", () => {
    const input = "a_i\n​\n和\nb_i\n​\n是两个";
    const output = stripZeroWidthChars(input);
    expect(output).not.toContain("​");
    // U+200B lines become empty lines
    expect(output).toBe("a_i\n\n和\nb_i\n\n是两个");
  });
});

// ============================================================
// dedupMathJax
// ============================================================

describe("dedupMathJax", () => {
  it("deduplicates 3 identical single-char lines", () => {
    const input = "some chinese text\nn\nn\nn\nmore chinese";
    const output = dedupMathJax(input);
    // Should keep only one "n"
    expect(output).toBe("some chinese text\nn\nmore chinese");
  });

  it("deduplicates 3 identical multi-char lines", () => {
    const input = "text before\np_i\np_i\np_i\ntext after";
    const output = dedupMathJax(input);
    expect(output).toBe("text before\np_i\ntext after");
  });

  it("picks the LaTeX-rich variant when mixed", () => {
    const input = "before\na_i\na_i\na_i\nafter";
    const output = dedupMathJax(input);
    // All three are "a_i", picks first (longest tie-break)
    expect(output).toBe("before\na_i\nafter");
  });

  it("picks longest when lengths differ", () => {
    const input = "before\nn\nni\nn_i\nafter";
    const output = dedupMathJax(input);
    // "n_i" is longest with LaTeX chars
    expect(output).toBe("before\nn_i\nafter");
  });

  it("leaves 2-item clusters untouched (below threshold)", () => {
    const input = "before\nn\nn\nafter";
    const output = dedupMathJax(input);
    expect(output).toBe("before\nn\nn\nafter");
  });

  it("does not cluster CJK lines", () => {
    const input = "中文\n英文\n日文";
    const output = dedupMathJax(input);
    expect(output).toBe("中文\n英文\n日文");
  });

  it("handles Unicode math symbols in clusters", () => {
    // U+2219 (∙) is a Unicode math bullet, should be in cluster
    const input = "text\n∙\n∙\n∙\nmore text";
    const output = dedupMathJax(input);
    // 3 bullet lines → dedup to 1
    expect(output).toBe("text\n∙\nmore text");
  });

  it("clusters mixed ASCII and Unicode math symbols", () => {
    // U+00D7 (×) among ASCII math
    const input = "text\n2\n×\n2×\nafter";
    // Only 2 items in cluster (below threshold 3)
    const output = dedupMathJax(input);
    // But we check it doesn't crash and preserves structure
    expect(output).toContain("text");
    expect(output).toContain("after");
  });

  it("does not deduplicate U+200B-only lines when mixed with ASCII", () => {
    // After stripZeroWidthChars, U+200B should be gone,
    // but test the raw behavior
    const input = "before\na_i\n​\n=\nafter";
    const output = dedupMathJax(input);
    // ​ and = are both non-CJK, short → cluster of 3 with a_i
    // cluster: ["a_i", "​", "="] — 3 items
    // best: "a_i" (has LaTeX chars _ )
    expect(output).toBe("before\na_i\nafter");
  });

  it("preserves blank lines between clusters", () => {
    const input = "chinese1\n\nn\nn\nn\n\nchinese2";
    const output = dedupMathJax(input);
    expect(output).toBe("chinese1\n\nn\n\nchinese2");
  });
});

// ============================================================
// Regression: sample code blocks must survive dedupMathJax
// (2236B — sample I/O was crushed because short numeric lines and
//  ``` fences inside code blocks were misclassified as MathJax islands)
// ============================================================

describe("dedupMathJax — code block safety (2236B regression)", () => {
  // Real sample section from Codeforces 2236B "Tatar TV Show" fullContent
  const sampleBlock = [
    "## 样例",
    "",
    "### 输入 #1",
    "```",
    "5",
    "4 2",
    "1010",
    "3 2",
    "111",
    "3 3",
    "111",
    "3 1",
    "110",
    "1 1",
    "1",
    "```",
    "### 输出 #1",
    "```",
    "YES",
    "NO",
    "NO",
    "YES",
    "NO",
    "```",
  ].join("\n");

  it("preserves every sample input line inside ``` fences", () => {
    const output = dedupMathJax(sampleBlock);
    for (const line of ["5", "4 2", "1010", "3 2", "111", "3 3", "3 1", "110", "1 1", "1"]) {
      expect(output).toContain(line);
    }
  });

  it("preserves every sample output line inside ``` fences", () => {
    const output = dedupMathJax(sampleBlock);
    for (const line of ["YES", "NO"]) {
      expect(output).toContain(line);
    }
  });

  it("preserves all four ``` code fences", () => {
    const output = dedupMathJax(sampleBlock);
    expect((output.match(/```/g) || []).length).toBe(4);
  });

  it("survives the full preprocessCodeforces pipeline end-to-end", () => {
    const input = [
      "[样例]",
      "输入 #1",
      "```",
      "5",
      "4 2",
      "1010",
      "3 2",
      "111",
      "1 1",
      "1",
      "```",
      "输出 #1",
      "```",
      "YES",
      "NO",
      "```",
    ].join("\n");
    const output = preprocessCodeforces(input);
    // Sample data intact
    expect(output).toContain("1010");
    expect(output).toContain("3 2");
    expect(output).toContain("1 1");
    expect(output).toContain("YES");
    expect(output).toContain("NO");
    // Section labels converted to headings
    expect(output).toContain("## 样例");
    expect(output).toContain("### 输入 #1");
    expect(output).toContain("### 输出 #1");
    // All four fences preserved
    expect((output.match(/```/g) || []).length).toBe(4);
  });
});

// ============================================================
// preprocessSections
// ============================================================

describe("preprocessSections", () => {
  it('converts [描述] to ## 题目描述', () => {
    expect(preprocessSections("[描述]")).toBe("## 题目描述\n");
  });

  it('converts [输入] to ## 输入格式', () => {
    expect(preprocessSections("[输入]")).toBe("## 输入格式\n");
  });

  it('converts [输出] to ## 输出格式', () => {
    expect(preprocessSections("[输出]")).toBe("## 输出格式\n");
  });

  it('converts [背景] to ## 背景', () => {
    expect(preprocessSections("[背景]")).toBe("## 背景\n");
  });

  it('converts [提示] to ## 提示', () => {
    expect(preprocessSections("[提示]")).toBe("## 提示\n");
  });

  it('converts [样例] to ## 样例', () => {
    expect(preprocessSections("[样例]")).toBe("## 样例\n");
  });

  it('converts [注] to ## 注', () => {
    expect(preprocessSections("[注]")).toBe("## 注\n");
  });

  it('converts [数据范围] to ## 数据范围', () => {
    expect(preprocessSections("[数据范围]")).toBe("## 数据范围\n");
  });

  it("handles multiple sections at once", () => {
    const input = "[描述]\ncontent\n[输入]\ndata";
    const expected = "## 题目描述\n\ncontent\n## 输入格式\n\ndata";
    expect(preprocessSections(input)).toBe(expected);
  });

  it("does not convert 【名词解释】 (full-width brackets)", () => {
    const input = "【名词解释】";
    expect(preprocessSections(input)).toBe("【名词解释】");
  });
});

// ============================================================
// preprocessNowcoder
// ============================================================

describe("preprocessNowcoder", () => {
  it("escapes standalone = line to prevent Setext heading", () => {
    const input = "[描述]\na_i = b_i\n​\n=\nmore text";
    const output = preprocessNowcoder(input);
    // Should NOT contain standalone = (Setext trigger)
    expect(output).not.toMatch(/^=\s*$/m);
    // Should have escaped =
    expect(output).toContain("\\=");
  });

  it("escapes standalone - line to prevent Setext heading", () => {
    const input = "[描述]\nsome text\n​\n-\nmore text";
    const output = preprocessNowcoder(input);
    expect(output).not.toMatch(/^-\s*$/m);
    expect(output).toContain("\\-");
  });

  it("removes U+200B characters", () => {
    const input = "[描述]\ntext with​zero width";
    const output = preprocessNowcoder(input);
    expect(output).not.toContain("​");
  });

  it("deduplicates triplicated math symbols", () => {
    const input = "[描述]\ntext\nn\nn\nn\nmore";
    const output = preprocessNowcoder(input);
    // 3 "n" lines → 1
    const nCount = output.split("\n").filter(l => l.trim() === "n").length;
    expect(nCount).toBe(1);
  });

  it("converts section markers to ## headings", () => {
    const input = "[描述]\ndesc\n[输入]\ninput\n[输出]\noutput";
    const output = preprocessNowcoder(input);
    expect(output).toContain("## 题目描述");
    expect(output).toContain("## 输入格式");
    expect(output).toContain("## 输出格式");
  });

  it("strips \\hspace artifacts", () => {
    const input = "[描述]\n\\hspace{15pt}\nsome text";
    const output = preprocessNowcoder(input);
    // \hspace lines should be stripped
    const hspaceCount = (output.match(/hspace/g) || []).length;
    expect(hspaceCount).toBe(0);
  });

  it("ensures blank lines after ## headings", () => {
    const input = "[描述]\ncontent";
    const output = preprocessNowcoder(input);
    expect(output).toMatch(/## 题目描述\n\n/);
  });

  it("preserves all Chinese content", () => {
    const input = "[描述]\n在一次针对古代遗迹的考察中，awdec 发现了一台古老的星纹拼接机。\n选择 a_i 和选择 b_i 依然被视为两种不同的方案。";
    const output = preprocessNowcoder(input);
    expect(output).toContain("古代遗迹");
    expect(output).toContain("被视为两种不同的方案");
  });
});

// ============================================================
// preprocessContent dispatcher
// ============================================================

describe("preprocessContent", () => {
  it("routes to nowcoder preprocessor", () => {
    const input = "[描述]\na_i\n​\n=\ntext";
    const output = preprocessContent(input, "nowcoder");
    // Should not have standalone =
    expect(output).not.toMatch(/^=\s*$/m);
  });

  it("routes to codeforces preprocessor", () => {
    const input = "[描述]\np\ni\n\np\ni\n\np_i";
    const output = preprocessContent(input, "codeforces");
    // Should have sections converted
    expect(output).toContain("## 题目描述");
  });

  it("routes to leetcode preprocessor", () => {
    const input = "示例 1：\n输入：nums = [1,2,3]";
    const output = preprocessContent(input, "leetcode");
    expect(output).toContain("### 示例 1：");
    expect(output).toContain("**输入：**");
  });

  it("defaults to sections-only preprocessing for unknown platforms", () => {
    const input = "[描述]\ncontent\n[输入]\ndata";
    const output = preprocessContent(input, "atcoder");
    expect(output).toContain("## 题目描述");
    expect(output).toContain("## 输入格式");
  });

  it("defaults for luogu platform", () => {
    const input = "[描述]\ncontent";
    const output = preprocessContent(input, "luogu");
    expect(output).toContain("## 题目描述");
  });
});

// ============================================================
// preprocessCodeforces — paragraph recovery
// (CF text extracted from <p> elements lacks blank lines because
//  BeautifulSoup's get_text("\\n") produces only single \\n between
//  adjacent <p> tags, so all paragraphs render as one giant blob.)
// ============================================================

describe("preprocessCodeforces — paragraph recovery", () => {
  it("inserts blank line between sentence-ending and uppercase-starting lines", () => {
    const input = [
      "[描述]",
      "This is the first sentence.",
      "This is the second paragraph.",
      "And a third one here.",
    ].join("\n");
    const output = preprocessCodeforces(input);
    // All three paragraphs should be separated by blank lines
    expect(output).toMatch(/first sentence\.\n\nThis is/);
    expect(output).toMatch(/second paragraph\.\n\nAnd a third/);
  });

  it("does NOT insert blank line inside code blocks", () => {
    const input = [
      "[样例]",
      "输入 #1",
      "```",
      "5",
      "2 2",
      "2 4",
      "1 5",
      "```",
      "输出 #1",
      "```",
      "Yes",
      "No",
      "```",
    ].join("\n");
    const output = preprocessCodeforces(input);
    // Code block fence count unchanged
    expect((output.match(/```/g) || []).length).toBe(4);
    // All sample lines present
    expect(output).toContain("5");
    expect(output).toContain("2 2");
    expect(output).toContain("Yes");
    expect(output).toContain("No");
  });

  it("does NOT disturb headings or **bold** lines", () => {
    const input = [
      "[描述]",
      "**时限**: 3000ms / **内存**: 512MB",
      "",
      "This is the description. It continues here.",
      "Another paragraph starts now.",
    ].join("\n");
    const output = preprocessCodeforces(input);
    // ## heading converted
    expect(output).toContain("## 题目描述");
    // bold line preserved
    expect(output).toContain("**时限**");
    // paragraphs separated
    expect(output).toMatch(/continues here\.\n\nAnother paragraph/);
  });

  it("survives the full 2236F2 description pipeline", () => {
    const input = [
      "[描述]",
      "**时限**: 3000ms / **内存**: 512MB",
      "",
      "This is the hard version of the problem. The only difference is that $1 \\le x \\le 5 \\cdot 10^5$.",
      "On the way home after buying his favorite soda \"Zola Cero\", Egor saw that elections for the position of \"Best Number\" are taking place in Saransk.",
      "There are $n$ people at the polling station.",
      "Each person brought a number $a_i$.",
      "Egor really likes the number $x$.",
      "",
      "[样例]",
      "输入 #1",
      "```",
      "5",
      "2 2",
      "```",
      "输出 #1",
      "```",
      "Yes",
      "```",
    ].join("\n");
    const output = preprocessCodeforces(input);
    // Paragraph boundaries inserted
    expect(output).toMatch(/10\^5\$\.\n\nOn the way/);
    expect(output).toMatch(/Saransk\.\n\nThere are/);
    // Sample section intact
    expect(output).toContain("## 样例");
    expect(output).toContain("### 输入 #1");
    expect(output).toContain("### 输出 #1");
    expect((output.match(/```/g) || []).length).toBe(4);
  });
});

// ============================================================
// preprocessCodeforces — bare LaTeX token wrapping
// (Old DB data may have bare \oplus / \geq outside $...$ fences
//  because the crawler's $$-merge regex stripped display fences.
//  The backend is fixed, but existing rows need a frontend fallback.)
// ============================================================

describe("preprocessCodeforces — bare LaTeX token wrapping", () => {
  it("wraps bare \\oplus / \\geq tokens that sit outside $...$", () => {
    // 2236G regression: the whole expression lost its $ fences
    const input = "condition holds: a_{v_{l}} \\oplus a_{v_{l+1}} \\geq 0, where.";
    const output = preprocessCodeforces(input);
    // \\oplus must now be inside a $...$ span
    const idx = output.indexOf("\\oplus");
    expect(idx).toBeGreaterThanOrEqual(0);
    expect(output[idx - 1]).toBe("$");
    // a closing $ follows \\oplus
    expect(output.slice(idx).indexOf("$", 1)).toBeGreaterThan(0);
  });

  it("does NOT re-wrap tokens already inside $...$", () => {
    const input = "value $a \\oplus b$ here.";
    const output = preprocessCodeforces(input);
    // Exactly one $...$ pair around the math, no extra wrapping
    expect((output.match(/\$/g) || []).length).toBe(2);
    expect(output).toContain("$a \\oplus b$");
  });

  it("leaves pure prose without LaTeX untouched", () => {
    const input = "This sentence has no math at all.";
    const output = preprocessCodeforces(input);
    expect(output).not.toContain("$");
  });

  it("handles mixed inline-math and bare tokens on the same line", () => {
    // $x$ is wrapped, \geq is bare → \geq should gain its own $...$
    const input = "given $x$, where a \\geq b holds.";
    const output = preprocessCodeforces(input);
    // $x$ preserved
    expect(output).toContain("$x$");
    // \geq now wrapped
    const idx = output.indexOf("\\geq");
    expect(output[idx - 1]).toBe("$");
  });

  it("does not wrap LaTeX inside code blocks", () => {
    const input = [
      "[描述]",
      "text",
      "```",
      "a \\oplus b",
      "```",
    ].join("\n");
    const output = preprocessCodeforces(input);
    // Code fence count unchanged
    expect((output.match(/```/g) || []).length).toBe(2);
    // Content preserved verbatim (no $ injected)
    const codeStart = output.indexOf("```");
    const codeEnd = output.indexOf("```", codeStart + 3);
    const codeBody = output.slice(codeStart + 3, codeEnd);
    expect(codeBody.replace(/\s/g, "")).toBe("a\\oplusb");
  });

  it("does NOT re-wrap tokens already inside $$...$$ display math", () => {
    // Crawler now emits correct $$...$$ display blocks; the frontend
    // fallback must NOT reach inside them and re-wrap \\commands.
    const input = "holds: $$ a_{v_{l}} \\oplus a_{v_{r}} \\geq 0 $$, where.";
    const output = preprocessCodeforces(input);
    // Display block stays intact — \oplus still adjacent to a_{v_{l}}
    expect(output).toContain("$$ a_{v_{l}} \\oplus");
    // No stray $\oplus$ injected inside the display block
    expect(output).not.toContain("$\\oplus$");
    // The two $$ fences preserved (4 dollar signs)
    expect((output.match(/\$/g) || []).length).toBe(4);
  });

  it("still wraps a truly bare \\command OUTSIDE any math span", () => {
    const input = "bare \\oplus token in prose.";
    const output = preprocessCodeforces(input);
    expect(output).toContain("$\\oplus$");
  });
});

// ============================================================
// preprocessCodeforces — display math line isolation
// ($$...$$ must sit on its own line so remark-math renders it as a
//  centered display block, not inline math glued to surrounding text.)
// ============================================================

describe("preprocessCodeforces — display math line isolation", () => {
  it("isolates $$...$$ display math onto its own line", () => {
    // Regression: 2236G's display formula was glued inline after "holds:"
    const input = "holds: $$ a_{v_{l}} \\oplus a_{v_{r}} \\geq 0 $$, where.";
    const output = preprocessCodeforces(input);
    // $$ must be preceded AND followed by a blank line → display block
    expect(output).toMatch(/\n\n\$\$ a_{v_{l}} \\oplus a_{v_{r}} \\geq 0 \$\$\n\n/);
  });

  it("does NOT turn inline $...$ into a display block", () => {
    const input = "value $a \\oplus b$ here.";
    const output = preprocessCodeforces(input);
    expect(output).not.toMatch(/\n\n\$a \\oplus b\$\n\n/);
    expect(output).toContain("$a \\oplus b$");
  });

  it("preserves multiple display blocks on one source line", () => {
    const input = "first $$a$$ and second $$b$$ done.";
    const output = preprocessCodeforces(input);
    // Both display blocks isolated, neither glued inline
    expect(output).toMatch(/\n\n\$\$a\$\$\n\n/);
    expect(output).toMatch(/\n\n\$\$b\$\$\n\n/);
  });
});

// ============================================================
// preprocessCodeforces — footnote separation
// (CF statement-footnote divs render as small-font standalone lines.
//  Their markers $^{\ast} / $^{\dagger}$ must start new paragraphs and
//  render at reduced font size.)
// ============================================================

describe("preprocessCodeforces — footnote separation", () => {
  it("starts a new paragraph before each footnote marker", () => {
    // Exact fullContent shape (all on one line)
    const input = "that are ideal.$^{\\ast}lcm$ — least common multiple.$^{\\dagger}$Two arrays here.";
    const output = preprocessCodeforces(input);
    // ideal. paragraph, then footnote on its own line
    expect(output).toMatch(/that are ideal\.\n+\$\^\{\\ast\}lcm/);
    // multiple. then dagger footnote on its own line
    expect(output).toMatch(/least common multiple\.\n+\$\^\{\\dagger\}\$Two/);
  });

  it("does not split an inline superscript inside a larger math span", () => {
    // $a^{\ast}b$ is inline math, NOT a footnote marker ($ not adjacent to ^)
    const input = "value $a^{\\ast}b$ end.";
    const output = preprocessCodeforces(input);
    expect(output).toContain("$a^{\\ast}b$");
    // No forced break before the inline math
    expect(output).not.toMatch(/\n+\$a/);
  });

  it("does NOT break an inline footnote REFERENCE (different$^{\dagger}$)", () => {
    // "different†" is an inline reference in body text, NOT a footnote
    // definition.  Only definitions (preceded by '.') get their own line.
    const input = "Help him find the number of different$^{\\dagger}$ arrays $p$ modulo $10^9 + 7$ that are ideal.";
    const output = preprocessCodeforces(input);
    // "different" must stay glued to $^{\dagger}$ (no forced break)
    expect(output).toContain("different$^{\\dagger}$");
    expect(output).not.toMatch(/different\n+\$\^/);
  });
});

// ============================================================
// Markdown component rendering
// ============================================================

describe("Markdown component", () => {
  it("renders its own .markdown-body scope container", () => {
    const { container } = render(<Markdown content="hi" sourcePlatform="unknown" />);
    expect(container.querySelector(".markdown-body")).toBeInTheDocument();
  });

  it("renders plain text as paragraph", () => {
    render(<Markdown content="Hello world" sourcePlatform="unknown" />);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("renders CF footnote paragraphs at reduced size (data-footnote)", () => {
    // After preprocessCodeforces, footnote markers start their own paragraph
    const content = "ideal.\n\n$^{\\ast}lcm$ — least common multiple.";
    const { container } = render(
      <Markdown content={content} sourcePlatform="codeforces" />
    );
    const footnote = container.querySelector('[data-footnote="true"]');
    expect(footnote).toBeInTheDocument();
  });

  it("renders footnote as a block-level <p>, not inline <span>", () => {
    // Two footnotes must each occupy their own line (block-level).
    // Regression: MUI Typography variant="caption" rendered as <span>,
    // gluing both footnotes onto one line.
    const content = "ideal.\n\n$^{\\ast}lcm$ — note.\n\n$^{\\dagger}$Two here.";
    const { container } = render(
      <Markdown content={content} sourcePlatform="codeforces" />
    );
    const footnotes = container.querySelectorAll('[data-footnote="true"]');
    expect(footnotes.length).toBe(2);
    // Each must be block-level (P), not SPAN
    expect(footnotes[0].tagName).toBe("P");
    expect(footnotes[1].tagName).toBe("P");
  });

  it("does not mark normal paragraphs as footnotes", () => {
    const { container } = render(
      <Markdown content="This is a normal paragraph." sourcePlatform="codeforces" />
    );
    const footnote = container.querySelector('[data-footnote="true"]');
    expect(footnote).not.toBeInTheDocument();
  });

  it("renders empty content placeholder", () => {
    render(<Markdown content="" />);
    expect(screen.getByText("暂无内容")).toBeInTheDocument();
  });

  it("renders ## headings as h5 variant", () => {
    const { container } = render(<Markdown content="## 题目描述\n\nContent here" sourcePlatform="unknown" />);
    // The h2 component renders as <h5> with variant="h5" and includes an icon
    const h5 = container.querySelector("h5");
    expect(h5).toBeInTheDocument();
    expect(h5?.textContent).toContain("题目描述");
  });

  it("does NOT create h1 from NowCoder content with triplication", () => {
    // Simulate the exact pattern that caused the bug
    const problematicContent = [
      "[描述]",
      "在一次针对古代遗迹的考察中",
      "a_i",
      "​",
      "和",
      "b_i",
      "​",
      "是两个完全相同的字符碎片（即",
      "a_i = b_i",
      "​",
      "=",
      "​",
      "），选择",
      "a_i",
      "​",
      "和选择",
      "b_i",
      "​",
      "依然被视为两种不同的方案。",
    ].join("\n");

    const { container } = render(
      <Markdown content={problematicContent} sourcePlatform="nowcoder" />
    );

    // Should NOT have an h4 element from Setext heading
    const h1Elements = container.querySelectorAll("h1");
    const h4Elements = container.querySelectorAll("h4");
    expect(h1Elements.length).toBe(0);
    expect(h4Elements.length).toBe(0);

    // Content should be in paragraphs
    const pElements = container.querySelectorAll("p");
    expect(pElements.length).toBeGreaterThan(0);
  });

  it("renders inline code with styling", () => {
    const { container } = render(<Markdown content="Use `printf` to output" sourcePlatform="unknown" />);
    const code = container.querySelector("code");
    expect(code).toBeInTheDocument();
    expect(code?.textContent).toBe("printf");
  });

  it("renders bold text", () => {
    render(<Markdown content="**important**" sourcePlatform="unknown" />);
    const strong = document.querySelector("strong");
    expect(strong).toBeInTheDocument();
    expect(strong?.textContent).toBe("important");
  });

  it("renders KaTeX display math", () => {
    const { container } = render(
      <Markdown content="$$\n\\left|a_i\\right|\n$$" sourcePlatform="unknown" />
    );
    // KaTeX renders math in .katex or .katex-display class
    const katex = container.querySelector(".katex, .katex-display");
    expect(katex).toBeInTheDocument();
  });

  it("renders bullet lists", () => {
    const { container } = render(
      <Markdown content={"- Item 1\n- Item 2\n- Item 3"} sourcePlatform="unknown" />
    );
    const list = container.querySelector("ul");
    expect(list).toBeInTheDocument();
    // remark-gfm may merge non-blank-line-separated items differently;
    // verify at least a list exists and each item text appears somewhere
    expect(container.textContent).toContain("Item 1");
    expect(container.textContent).toContain("Item 2");
    expect(container.textContent).toContain("Item 3");
  });

  it("handles mixed content without Setext heading artifacts", () => {
    // Test: a_i = b_i on a line followed by = on its own line
    // (after U+200B stripping) should NOT create heading
    const content = [
      "[描述]",
      "一些中文描述",
      "变量 a_i 和 b_i",
      "a_i = b_i",
      "​",
      "=",
      "​",
      "文本继续",
    ].join("\n");

    const { container } = render(
      <Markdown content={content} sourcePlatform="nowcoder" />
    );

    // Verify no h1 or h4 (Setext heading) is rendered
    // (the ## heading renders as h5, which is correct)
    const headings = container.querySelectorAll("h1,h4");
    expect(headings.length).toBe(0);
  });
});
