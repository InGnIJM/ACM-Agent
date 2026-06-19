/**
 * Shared pure helpers for building the `full_content` blob from a crawl record.
 *
 * Previously this logic lived inline inside {@link CrawlerController} as four
 * private instance methods, and was then copy-pasted into the data-migration
 * scripts (`backend/src/crawler/import-problems.ts`,
 * `backend/scripts/import-318732.ts`, `backend/scripts/reimport-two-sum.ts`).
 * The duplication is what allowed the AtCoder data-loss bug to recur: each
 * copy drifted. Extracting a single pure module here lets every caller
 * (controller + future migration script) reuse the exact same logic.
 *
 * Section A of the fix: extraction.
 * Section B: platform gate (skip cleanMathJaxTriplication for atcoder/luogu).
 * Section C: code-fence awareness inside cleanMathJaxTriplication.
 * Section D: over-aggressive empty-math regexes → whole-line-only.
 * Section E: camelCase alias support for the divergent crawler schemas.
 */

/**
 * Parse a flat sample string (from NowCoder) into [[input, output], ...].
 * Looks for patterns like "输入：... 输出：..." or "示例1：输入...输出...".
 */
export function parseSampleString(text: string): any[] | null {
  if (!text) return null;
  // Try to split by common NowCoder sample markers
  const pairs: any[] = [];
  // Pattern: 输入[:：]\s*(.+?)\s*输出[:：]\s*(.+?)(?=输入|示例|$)
  const regex = /输入\s*[:：]\s*([\s\S]*?)\s*输出\s*[:：]\s*([\s\S]*?)(?=\n\s*输入|\n\s*示例|$)/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    pairs.push([match[1].trim(), match[2].trim()]);
  }
  if (pairs.length > 0) return pairs;
  // Fallback: look for 示例 / sample markers
  const regex2 = /示例\s*\d+\s*[:：]?\s*输入\s*[:：]?\s*([\s\S]*?)\s*输出\s*[:：]?\s*([\s\S]*?)(?=示例\s*\d|$)/g;
  while ((match = regex2.exec(text)) !== null) {
    pairs.push([match[1].trim(), match[2].trim()]);
  }
  return pairs.length > 0 ? pairs : null;
}

/**
 * Extract sample Input/Output pairs from LeetCode's HTML content.
 *
 * Supports two LeetCode page formats:
 *   OLD: <pre><strong>Input:</strong> ... <strong>Output:</strong> ...</pre>
 *   NEW: <p><strong>输入：</strong><span class="example-io">...</span></p>
 *        <p><strong>输出：</strong><span class="example-io">...</span></p>
 *
 * This parser extracts those pairs BEFORE the HTML is stripped.
 */
export function parseLeetCodeSamples(html: string): Array<[string, string, string?]> | null {
  if (!html) return null;
  const pairs: Array<[string, string, string?]> = [];

  // ── Pass 1: old <pre> format ────────────────────────────────
  // LeetCode CN HTML is: <pre>\n<strong>输入：</strong>…\n<strong>输出：</strong>…
  //   — note the NEWLINE right after <pre>, and Chinese full-width "：".
  // So \s* MUST come before the optional <strong>, and the colon class
  // accepts both ASCII ":" and full-width "：".
  const preRegex = /<pre>\s*(?:<strong>)?\s*(?:Input|输入)\s*[：:]?\s*(?:<\/strong>)?\s*([\s\S]*?)\s*(?:<strong>)?\s*(?:Output|输出)\s*[：:]?\s*(?:<\/strong>)?\s*([\s\S]*?)\s*<\/pre>/gi;
  let match: RegExpExecArray | null;
  while ((match = preRegex.exec(html)) !== null) {
    let input = (match[1] || '').replace(/<[^>]+>/g, '').trim();
    let output = (match[2] || '').replace(/<[^>]+>/g, '').trim();
    // Extract the explanation (Explanation/解释) as the optional 3rd
    // element before discarding it from the output.
    let note: string | undefined;
    const noteIdx = output.search(/(?:Explanation|解释)/i);
    if (noteIdx >= 0) {
      note = output
        .slice(noteIdx)
        .replace(/^(?:Explanation|解释)\s*[：:]?\s*/, '')
        .trim();
      output = output.slice(0, noteIdx).trim();
    }
    if (input || output) pairs.push([input, output, note]);
  }

  // ── Pass 2: new <div class="example-block"> format (LeetCode CN current) ──
  if (pairs.length === 0) {
    // Split by example-block boundaries so each block is parsed independently
    const blocks = html.split(/<div[^>]*class="example-block"[^>]*>/gi);
    for (const block of blocks) {
      // Extract input: <strong>输入：</strong> or <b>Input:</b> followed by value
      const inM = block.match(
        /<(?:strong|b)>\s*(?:输入|Input)\s*：?\s*:?\s*<\/(?:strong|b)>\s*(?:<span[^>]*class="example-io"[^>]*>)?([\s\S]*?)(?:<\/span>)?\s*<\/p>/i,
      );
      // Extract output: <strong>输出：</strong> or <b>输出：</b> (may be inside <span class="example-io">)
      const outM = block.match(
        /(?:<span[^>]*class="example-io"[^>]*>)?<(?:strong|b)>\s*(?:输出|Output)\s*：?\s*:?\s*<\/(?:strong|b)>\s*(?:<span[^>]*class="example-io"[^>]*>)?([\s\S]*?)(?:<\/span>)?\s*<\/p>/i,
      );
      if (inM && outM) {
        const input = inM[1].replace(/<[^>]+>/g, '').trim();
        const output = outM[1].replace(/<[^>]+>/g, '').trim();
        if (input || output) pairs.push([input, output]);
      }
    }
  }

  return pairs.length > 0 ? pairs : null;
}

/**
 * Convert HTML to plain text using the same pipeline as buildFullContent.
 * Includes <sup>/<sub> → LaTeX conversion, tag stripping, entity decoding,
 * and whitespace normalisation.
 */
export function htmlToPlainText(html: string): string {
  if (!html) return '';
  return html
    // sup/sub → LaTeX math
    .replace(/([A-Za-z0-9.\-]+)<sup>([^<]+)<\/sup>/gi, (_m: string, p: string, x: string) => `$${p}^{${x}}$`)
    .replace(/([A-Za-z0-9.\-]+)<sub>([^<]+)<\/sub>/gi, (_m: string, p: string, x: string) => `$${p}_{${x}}$`)
    // block-level closing tags → newlines
    .replace(/<\/(?:p|div|li|h[1-6]|pre|blockquote|section|article|main|aside|header|footer|nav|figure|figcaption|details|summary|fieldset|form|table|tr|ul|ol|dl)>/gi, '\n')
    .replace(/<(?:br|hr)\b[^>]*\/?>/gi, '\n')
    // block-level opening tags → newlines
    .replace(/<\/?(?:p|div|h[1-6]|pre|blockquote|li|tr|ul|ol|dl|table|section|article|main|aside|header|footer|nav)\b[^>]*>/gi, '\n')
    // strip remaining inline tags
    // CRITICAL: encode standalone < that is not part of a tag first
    // (e.g. "<= x" in code blocks — the < is literal text, not a tag opener).
    // Without this, /<[^>]+>/g greedily matches from <= to the next >,
    // destroying all the text in between.
    .replace(/<(?![a-zA-Z\/])/g, '&lt;')
    .replace(/<[^>]+>/g, '')
    // decode entities
    .replace(/&#39;/g, "'").replace(/&#x27;/g, "'").replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ')
    .replace(/&#8217;/g, "'").replace(/&#8216;/g, "'")
    .replace(/&#8220;/g, '"').replace(/&#8221;/g, '"')
    .replace(/&#8230;/g, '...').replace(/&#xA0;/g, ' ')
    // whitespace normalisation
    .replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n')
    .replace(/\n{3,}/g, '\n\n').trim();
}

/**
 * Clean MathJax triplication artifacts from scraped CF/NowCoder text.
 *
 * OJ pages render each math expression 3 ways (plain-text preview, LaTeX
 * source, rendered <nobr>).  After HTML stripping, the same math fragment
 * can appear 2-3 times separated by blank lines:
 *   f               <- plain-text char
 *   (               <- plain-text char
 *   f(·)            <- LaTeX-source line (the one we want)
 *
 * Multi-pass strategy:
 * 1. Collapse isolated single-char math lines between blank lines into
 *    a joined line (the LaTeX-source variant is typically the longest).
 * 2. Deduplicate repeated lines within a cluster (keep longest/LaTeX-rich).
 * 3. Wrap surviving LaTeX commands in $…$ for KaTeX rendering.
 * 4. Normalise whitespace.
 *
 * Defense-in-depth: code-fence-aware (``` / ~~~). While inside a fenced code
 * block, every line is pushed verbatim and math-fragment detection is skipped
 * — mirrors frontend `dedupMathJax()` in
 * frontend/src/components/common/Markdown.tsx. Regression: Codeforces 2236B
 * sample I/O was crushed because short numeric lines (5, 4 2, 111, …) inside
 * ``` fences all matched isMathFragment, so multi-line samples collapsed to
 * one line and the closing fences were swallowed.
 */
export function cleanMathJaxTriplication(text: string): string {
  if (!text) return text;

  // ── Pre-pass: collapse blank lines between math-fragment lines ──
  // CF pages produce patterns like:
  //   "...that \n\n1\n\n≤\n\nx\n\n1 \le x\n\n."   (each symbol on its own line)
  // This step merges blank-line-separated math fragments into
  // contiguous groups so the cluster dedup below can find them.
  {
    const lines = text.split('\n');
    const merged: string[] = [];
    let i = 0;
    // Track fenced code blocks (``` / ~~~) so their contents are preserved
    // verbatim and never misclassified as MathJax triplication islands.
    let inCodeBlock = false;

    const MATH_CHAR = /[\\_{}^|×∙∣≤≥±∞∑∏∫∂∇√≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ]/;
    const isMathFragment = (s: string): boolean => {
      if (!s || s.length > 120) return false;
      if (/^[\[【#]/.test(s)) return false;
      if (/[一-鿿]/.test(s)) return false;
      if (s.length <= 3) {
        return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞∑∏∫∂∇√≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ​]+$/.test(s);
      }
      if (!MATH_CHAR.test(s)) return false;
      return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞∑∏∫∂∇√≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ​]+$/.test(s);
    };

    while (i < lines.length) {
      const t = lines[i].trim();

      // Fenced code blocks (``` or ~~~) toggle the in-fence flag; their
      // contents must NOT be misclassified as MathJax triplication islands.
      if (t.startsWith('```') || t.startsWith('~~~')) {
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

      if (t === '' || !isMathFragment(t)) {
        merged.push(lines[i]);
        i++;
        continue;
      }

      // Start of a math island — collect all math fragments,
      // skipping blank lines between them.
      const island: string[] = [lines[i]];
      i++;
      while (i < lines.length) {
        const s = lines[i].trim();
        // Never let an island cross a code fence.
        if (s.startsWith('```') || s.startsWith('~~~')) break;
        if (s === '') {
          // Peek ahead: is the next non-blank line also math?
          let peek = i + 1;
          while (peek < lines.length && lines[peek].trim() === '') peek++;
          if (peek < lines.length && isMathFragment(lines[peek].trim())) {
            i++; // skip this blank — it separates two math fragments
            continue;
          }
          // Blank not between math fragments — keep it, end island
          break;
        }
        if (isMathFragment(s)) {
          island.push(lines[i]);
          i++;
        } else {
          break;
        }
      }

      // Deduplicate the island
      if (island.length >= 3) {
        const latexLines = island.map(l => l.trim()).filter(l => /\\[a-zA-Z]/.test(l));
        if (latexLines.length > 0) {
          const best = latexLines.reduce((a, b) =>
            b.length > a.length ? b : a
          );
          merged.push(best);
        } else {
          const unique = [...new Set(island.map(l => l.trim()))];
          merged.push(unique.reduce((a, b) => b.length > a.length ? b : a));
        }
      } else {
        merged.push(...island.map(l => l.trim()));
      }
    }

    text = merged.join('\n');
  }

  // ── Post-pass: wrap LaTeX lines in $…$ for KaTeX ──────────
  if (!text.includes('$')) {
    text = text.replace(
      /^(.*\\[a-zA-Z].*)$/gm,
      (_m: string, line: string) => {
        if (line.includes('$')) return _m;
        return `$${line.trim()}$`;
      }
    );
  }

  // ── Final whitespace normalisation ────────────────────────
  text = text
    .replace(/\\,/g, '')   // thin space
    .replace(/\\!/g, '')   // negative thin space
    .replace(/\\;/g, '')   // thick space
    .replace(/\\:/g, '')   // medium space
    // Section D: only strip a standalone empty math delimiter that occupies
    // a WHOLE line. Previously these were global (`/\$\$/g`, `/\$ \$/g`) and
    // the second one matched the middle of adjacent inline math like
    // "$H$ $W$" — collapsing it to "$HW$" and destroying data.
    .replace(/^\s*\$\$\s*$/gm, '')   // whole-line empty display math
    .replace(/^\s*\$\s*\$\s*$/gm, '') // whole-line empty inline math
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return text;
}

/**
 * Build the `full_content` blob from a crawl record using the standard
 * section format ([背景] / [描述] / [数据范围] / [输入] / [输出] / [样例] /
 * [提示] / [注]).
 *
 * @param platform lowercase OJ id: 'codeforces' | 'leetcode' | 'nowcoder'
 *   | 'luogu' | 'atcoder' | ...
 * @param record   raw crawled record. Supports BOTH snake_case
 *   ({@link record.input_format}, {@link record.output_format}) AND camelCase
 *   ({@link record.inputFormat}, {@link record.outputFormat}) schemas — the
 *   AtCoder crawler (1202Contest_j) stores the latter. Limits support
 *   {@code limits.time} / {@code limits.timeLimit} / top-level
 *   {@code timeLimit}, and likewise for memory.
 */
export function buildFullContent(platform: string, record: any): string {
  const parts: string[] = [];

  // Section B: AtCoder and Luogu data is already clean $…$ KaTeX — running
  // the triplication cleaner on it misclassifies short constraint lines like
  // "$1 \leq H \leq 20$", "|", "or", "-", "." as a 3-copy math island and
  // DELETES them (verified on 1202Contest_b). Skip the cleaner for those.
  const skipMathClean = platform === 'atcoder' || platform === 'luogu';
  const clean = (t: any): string =>
    skipMathClean ? (t ?? '') : cleanMathJaxTriplication(t);

  if (record.background) parts.push(`[背景]\n${clean(record.background)}`);

  // Build description with optional limits header (Issue #6)
  // Supports both naming conventions:
  //   record.limits.{time,memory}        (CF crawler, ms/MB)
  //   record.limits.{timeLimit,memoryLimit}  (API-originated variants)
  //   record.{timeLimit,memoryLimit}     (AtCoder camelCase schema)
  let desc = record.description || '';
  const limits = record.limits;
  if (limits) {
    const timeVal = limits.time ?? limits.timeLimit ?? null;
    const memVal = limits.memory ?? limits.memoryLimit ?? null;
    if (timeVal != null || memVal != null) {
      const timeMs = timeVal != null ? `${timeVal}ms` : '?';
      const memMb = memVal != null ? `${memVal}MB` : '?';
      desc = desc ? `**时限**: ${timeMs} / **内存**: ${memMb}\n\n${desc}` : `**时限**: ${timeMs} / **内存**: ${memMb}`;
    }
  }
  // Section E: top-level camelCase timeLimit/memoryLimit fallback
  // (AtCoder 1202Contest_j has NO limits object — only flat fields).
  if (!limits) {
    const timeVal = record.timeLimit ?? null;
    const memVal = record.memoryLimit ?? null;
    if (timeVal != null || memVal != null) {
      const timeMs = timeVal != null ? `${timeVal}ms` : '?';
      const memMb = memVal != null ? `${memVal}MB` : '?';
      desc = desc ? `**时限**: ${timeMs} / **内存**: ${memMb}\n\n${desc}` : `**时限**: ${timeMs} / **内存**: ${memMb}`;
    }
  }
  if (desc) parts.push(`[描述]\n${clean(desc)}`);

  // Issue #5: constraints → [数据范围]
  if (record.constraints) {
    parts.push(`[数据范围]\n${clean(record.constraints)}`);
  }

  // Section E: read BOTH snake_case and camelCase aliases — AtCoder crawler
  // (1202Contest_j) stores inputFormat/outputFormat instead of
  // input_format/output_format.
  const inputFormat = record.input_format ?? record.inputFormat;
  const outputFormat = record.output_format ?? record.outputFormat;

  // LeetCode: no separate input/output format — everything is in HTML content
  if (inputFormat && platform !== 'leetcode') parts.push(`[输入]\n${clean(inputFormat)}`);
  if (outputFormat && platform !== 'leetcode') parts.push(`[输出]\n${clean(outputFormat)}`);

  // Samples: separate input/output code blocks — standard OJ order: samples before hints
  if (record.samples) {
    // Normalize dict-type samples (e.g. {"0":[in,out],"1":[in,out]}) to array
    if (!Array.isArray(record.samples) && typeof record.samples === 'object' && record.samples !== null) {
      record.samples = Object.values(record.samples);
    }
    if (Array.isArray(record.samples) && record.samples.length > 0) {
      const sampleLines = record.samples.map((s: any, i: number) => {
        if (Array.isArray(s)) {
          const inputBlock = `输入 #${i + 1}\n\`\`\`\n${s[0] || ''}\n\`\`\``;
          const outputBlock = `输出 #${i + 1}\n\`\`\`\n${s[1] || ''}\n\`\`\``;
          if (s[2] && String(s[2]).trim()) {
            return inputBlock + '\n\n' + outputBlock + '\n\n' +
              `解释 #${i + 1}\n\n${String(s[2]).trim()}`;
          }
          return inputBlock + '\n\n' + outputBlock;
        }
        return String(s);
      });
      parts.push(`[样例]\n${sampleLines.join('\n\n')}`);
    } else if (typeof record.samples === 'string' && record.samples.trim()) {
      // Issue #1: NowCoder string samples — try to parse into structured format
      const parsed = parseSampleString(record.samples);
      if (parsed && parsed.length > 0) {
        const sampleLines = parsed.map((s: any, i: number) => {
          if (Array.isArray(s)) {
            const inputBlock = `输入 #${i + 1}\n\`\`\`\n${s[0] || ''}\n\`\`\``;
            const outputBlock = `输出 #${i + 1}\n\`\`\`\n${s[1] || ''}\n\`\`\``;
            if (s[2] && String(s[2]).trim()) {
              return inputBlock + '\n\n' + outputBlock + '\n\n' +
                `解释 #${i + 1}\n\n${String(s[2]).trim()}`;
            }
            return inputBlock + '\n\n' + outputBlock;
          }
          return String(s);
        });
        parts.push(`[样例]\n${sampleLines.join('\n\n')}`);
      } else {
        parts.push(`[样例]\n${record.samples}`);
      }
    }
  }
  // Issue #3: LeetCode hints array
  if (record.hints && Array.isArray(record.hints) && record.hints.length > 0) {
    const hintText = record.hints.map((h: string, i: number) => `${i + 1}. ${h}`).join('\n');
    parts.push(`[提示]\n${hintText}`);
  } else if (record.hint) {
    parts.push(`[提示]\n${clean(record.hint)}`);
  }
  if (record.note) parts.push(`[注]\n${record.note}`);
  // Decode HTML content (LeetCode returns HTML in content field)
  let description = record.content || record.description || '';
  // Hints extracted from HTML content (used when GraphQL hints is empty)
  let extractedHintsHtml: string | null = null;
  if (description && description.trim().startsWith('<')) {
    // ── Step 0: remove example blocks (parsed separately by
    // parseLeetCodeSamples) so they don't leak into [描述] ──
    if (platform === 'leetcode') {
      // Old format: <pre> with Input/Output inside
      description = description.replace(
        /<pre>(?:<strong>)?\s*(?:Input|输入)\s*:?\s*(?:<\/strong>)?\s*[\s\S]*?\s*(?:<strong>)?\s*(?:Output|输出)\s*:?\s*(?:<\/strong>)?\s*[\s\S]*?\s*<\/pre>/gi,
        '',
      );
      // New format: <div class="example-block"> containing I/O + explanation
      description = description.replace(
        /<div[^>]*class="example-block"[^>]*>[\s\S]*?<\/div>/gi,
        '',
      );
      // Remove orphaned <pre> explanation blocks (leftover from new format)
      description = description.replace(
        /<pre>[\s\S]*?<\/pre>/gi,
        '',
      );
      // Remove orphaned example/tip label elements outside example-block
      // e.g. <strong class="example">示例 1：</strong> (old format)
      description = description.replace(
        /<(?:strong|b)\s[^>]*class="example"[^>]*>.*?<\/(?:strong|b)>/gi,
        '',
      );
      // Also catch plain <strong>/<b> example headers without class (new format)
      // e.g. <strong>示例 1：</strong>, <strong>示例&nbsp;3：</strong>,
      //      <strong>Example 1:</strong>
      description = description.replace(
        /<(?:strong|b)>\s*(?:示例(?:\s*&nbsp;\s*)?\s*\d*\s*[：:]|Example\s*\d*\s*:)\s*<\/(?:strong|b)>/gi,
        '',
      );
      // ── Extract hints <ul> block from HTML (LeetCode GraphQL hints
      // is often empty, but the hints are embedded in the HTML content).
      // MUST run before the label-stripping fallback below. ──
      const hintSectionRe = /<(?:strong|b)>\s*(?:提示|Hint|Note|Constraints)\s*[：:]?\s*<\/(?:strong|b)>\s*<\/p>\s*(<ul\b[\s\S]*?<\/ul>)/i;
      const hintMatch = description.match(hintSectionRe);
      if (hintMatch) {
        extractedHintsHtml = hintMatch[1];
        // Remove the entire hints section (label + <ul> block) from description
        description = description.replace(
          /<(?:strong|b)>\s*(?:提示|Hint|Note|Constraints)\s*[：:]?\s*<\/(?:strong|b)>\s*<\/p>\s*<ul\b[\s\S]*?<\/ul>/i,
          '',
        );
      } else {
        // No <ul> block — just strip the label (legacy, e.g. hints in plain text)
        description = description.replace(
          /<(?:strong|b)>(?:提示|Note|Constraints|Hint)\s*[：:]?\s*<\/(?:strong|b)>/gi,
          '',
        );
      }
    }
    // ── Step 1: convert <sup>/<sub> to inline LaTeX math BEFORE tag stripping ──
    // Wrap "prefix token + exponent/index" in $…$ so KaTeX renders it.
    //   10<sup>4</sup>   → $10^{4}$
    //   -10<sup>9</sup>  → $-10^{9}$   (minus captured into the math span)
    //   O(n<sup>2</sup>) → O($n^{2}$) (local wrap; O() stays as text)
    //   a<sub>i</sub>    → $a_{i}$
    // Function-replacement avoids JS `$`-escaping pitfalls in the
    // replacement string. `<=` / `>=` are left as literal text.
    description = description
      .replace(/([A-Za-z0-9.\-]+)<sup>([^<]+)<\/sup>/gi, (_m: string, p: string, x: string) => `$${p}^{${x}}$`)
      .replace(/([A-Za-z0-9.\-]+)<sub>([^<]+)<\/sub>/gi, (_m: string, p: string, x: string) => `$${p}_{${x}}$`);
    // ── Step 2: block-level tags → paragraph breaks ──────
    // CRITICAL: strip tags BEFORE entity decoding to prevent
    // decoded '<' chars (from &lt;) being parsed as HTML tag openers.
    // e.g. "3 &lt;= nums.length" → first strip tags (nothing to strip),
    // then decode &lt; → "3 <= nums.length" (correct).
    description = description
      .replace(/<\/(?:p|div|li|h[1-6]|pre|blockquote|section|article|main|aside|header|footer|nav|figure|figcaption|details|summary|fieldset|form|table|tr|ul|ol|dl)>/gi, '\n')
      .replace(/<(?:br|hr)\b[^>]*\/?>/gi, '\n')
      .replace(/<\/?(?:p|div|h[1-6]|pre|blockquote|li|tr|ul|ol|dl|table|section|article|main|aside|header|footer|nav)\b[^>]*>/gi, '\n');
    // ── Step 3: remove remaining tags (inline elements) ──
    // Encode standalone < first (see htmlToPlainText for rationale)
    description = description.replace(/<(?![a-zA-Z\/])/g, '&lt;');
    description = description.replace(/<[^>]+>/g, '');
    // ── Step 4: decode numeric & named entities ──────────
    // Now safe: any '<' in the text was originally &lt; and
    // survived tag stripping as the encoded form.
    description = description
      .replace(/&#39;/g, "'")
      .replace(/&#x27;/g, "'")
      .replace(/&apos;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&')
      .replace(/&nbsp;/g, ' ')
      .replace(/&#8217;/g, "'")
      .replace(/&#8216;/g, "'")
      .replace(/&#8220;/g, '"')
      .replace(/&#8221;/g, '"')
      .replace(/&#8230;/g, '...')
      .replace(/&#xA0;/g, ' ');
    // ── Step 5: whitespace normalisation ───────────────────
    description = description
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n[ \t]+/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }
  // For LeetCode: parse examples from HTML content (contains real Input/Output pairs)
  // Always try HTML parsing first; it produces real output data unlike Python's input-only samples
  if (platform === 'leetcode') {
    const htmlContent = record.content || '';
    const parsedSamples = parseLeetCodeSamples(htmlContent);
    if (parsedSamples && parsedSamples.length > 0) {
      // Override any previously-added [样例] from Python samples
      for (let i = parts.length - 1; i >= 0; i--) {
        if (parts[i].startsWith('[样例]')) {
          parts.splice(i, 1);
        }
      }
      const sampleLines = parsedSamples.map((s: any, i: number) => {
        if (Array.isArray(s)) {
          // ### headers (not bare "输入 #N") so the frontend's
          // preprocessSections regex (which matches lines starting with
          // "输入") won't double-convert these.
          let block =
            `### 输入 #${i + 1}\n\`\`\`\n${s[0] || ''}\n\`\`\`\n\n` +
            `### 输出 #${i + 1}\n\`\`\`\n${s[1] || ''}\n\`\`\`\n`;
          // Explanation block only when the 3rd element is non-empty.
          const note = s[2];
          if (note && String(note).trim()) {
            block += `\n### 解释 #${i + 1}\n\`\`\`\n${String(note).trim()}\n\`\`\`\n`;
          }
          return block;
        }
        return String(s);
      });
      parts.push(`[样例]\n${sampleLines.join('\n\n')}`);
    } else if (!record.samples) {
      // Fallback: only show sampleTestCase as input (exampleTestcases is NOT output)
      const sampleTestCase = record.sampleTestCase || '';
      if (sampleTestCase) {
        parts.push(`[样例]\n输入 #1\n\`\`\`\n${sampleTestCase}\n\`\`\``);
      }
    }
  }
  // ── If GraphQL hints was empty, use hints extracted from HTML content ──
  if (extractedHintsHtml) {
    const hasRecordHints = record.hints && Array.isArray(record.hints) && record.hints.length > 0;
    if (!hasRecordHints && !record.hint) {
      const hintsText = htmlToPlainText(extractedHintsHtml);
      if (hintsText) {
        parts.push(`[提示]\n${hintsText}`);
      }
    }
  }
  // Wrap plain text content with [描述] section marker
  if (description && !record.description) {
    parts.unshift(`[描述]\n${description}`);
  }
  return parts.length > 0 ? parts.join('\n\n') : (description || '');
}
