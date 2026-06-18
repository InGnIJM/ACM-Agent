/**
 * ONE-OFF reimport script: recompute `full_content` for the two-sum problem
 * (id=fbc09d59-bb78-498c-9e5f-d19f9ed7c1b9) from its stored `raw_detail`
 * using the FIXED LeetCode conversion logic that lives in
 * `backend/src/crawler/crawler.controller.ts` (buildFullContent +
 * parseLeetCodeSamples + cleanMathJaxTriplication).
 *
 * Why this script instead of `import-problems.ts`:
 *   `import-problems.ts` ships STALE copies of those helpers (still emits
 *   `10^4`, doesn't extract Explanation, uses bare "输入 #N" headers).  Using
 *   it would regenerate the SAME broken content.  This script is a faithful
 *   copy of the controller's CURRENT (fixed) logic so we don't touch the
 *   controller source or re-crawl leetcode.cn.
 *
 * Usage:
 *   cd backend && npx tsx scripts/reimport-two-sum.ts
 *
 * Scope: a SINGLE problem (hard-coded id below).  No batch changes.
 */
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const PROBLEM_ID = 'fbc09d59-bb78-498c-9e5f-d19f9ed7c1b9';

// ═══════════════════════════════════════════════════════════════════════
//  parseLeetCodeSamples  — verbatim copy from crawler.controller.ts
//  (returns [input, output, note?] triples; note = Explanation/解释 text)
// ═══════════════════════════════════════════════════════════════════════
function parseLeetCodeSamples(html: string): Array<[string, string, string?]> | null {
  if (!html) return null;
  const pairs: Array<[string, string, string?]> = [];

  // ── Pass 1: old <pre> format ────────────────────────────────
  const preRegex = /<pre>\s*(?:<strong>)?\s*(?:Input|输入)\s*[：:]?\s*(?:<\/strong>)?\s*([\s\S]*?)\s*(?:<strong>)?\s*(?:Output|输出)\s*[：:]?\s*(?:<\/strong>)?\s*([\s\S]*?)\s*<\/pre>/gi;
  let match: RegExpExecArray | null;
  while ((match = preRegex.exec(html)) !== null) {
    let input = (match[1] || '').replace(/<[^>]+>/g, '').trim();
    let output = (match[2] || '').replace(/<[^>]+>/g, '').trim();
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

  // ── Pass 2: new <div class="example-block"> format ──
  if (pairs.length === 0) {
    const blocks = html.split(/<div[^>]*class="example-block"[^>]*>/gi);
    for (const block of blocks) {
      const inM = block.match(
        /<(?:strong|b)>\s*(?:输入|Input)\s*：?\s*:?\s*<\/(?:strong|b)>\s*(?:<span[^>]*class="example-io"[^>]*>)?([\s\S]*?)(?:<\/span>)?\s*<\/p>/i,
      );
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

// ═══════════════════════════════════════════════════════════════════════
//  cleanMathJaxTriplication  — verbatim copy from crawler.controller.ts
//  (not exercised for two-sum — no background/desc/constraints/hint fields —
//   but kept faithful so the script mirrors the controller exactly)
// ═══════════════════════════════════════════════════════════════════════
function cleanMathJaxTriplication(text: string): string {
  if (!text) return text;
  {
    const lines = text.split('\n');
    const merged: string[] = [];
    let i = 0;

    const MATH_CHAR = /[\\_{}^|×∙∣≤≥±∞∑∏∫∂∇√≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ]/;
    const isMathFragment = (s: string): boolean => {
      if (!s || s.length > 120) return false;
      if (/^[\[【#]/.test(s)) return false;
      if (/[一-鿿]/.test(s)) return false;
      if (s.length <= 3) {
        return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞∑∏∫∂∇√∞≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ​]+$/.test(s);
      }
      if (!MATH_CHAR.test(s)) return false;
      return /^[a-zA-Z0-9\s_{}^+\-*/=<>().,|\\;!@#$%&:'"×∙∣≤≥±∞∑∏∫∂∇√∞≈≠←→⇒⇔⋅⋯⋮⋱αβγθλμπστφωΓΔΘΛΠΣΦΩ​]+$/.test(s);
    };

    while (i < lines.length) {
      const t = lines[i].trim();

      if (t === '' || !isMathFragment(t)) {
        merged.push(lines[i]);
        i++;
        continue;
      }

      const island: string[] = [lines[i]];
      i++;
      while (i < lines.length) {
        const s = lines[i].trim();
        if (s === '') {
          let peek = i + 1;
          while (peek < lines.length && lines[peek].trim() === '') peek++;
          if (peek < lines.length && isMathFragment(lines[peek].trim())) {
            i++;
            continue;
          }
          break;
        }
        if (isMathFragment(s)) {
          island.push(lines[i]);
          i++;
        } else {
          break;
        }
      }

      if (island.length >= 3) {
        const latexLines = island.map(l => l.trim()).filter(l => /\\[a-zA-Z]/.test(l));
        if (latexLines.length > 0) {
          const best = latexLines.reduce((a, b) => (b.length > a.length ? b : a));
          merged.push(best);
        } else {
          const unique = [...new Set(island.map(l => l.trim()))];
          merged.push(unique.reduce((a, b) => (b.length > a.length ? b : a)));
        }
      } else {
        merged.push(...island.map(l => l.trim()));
      }
    }

    text = merged.join('\n');
  }

  if (!text.includes('$')) {
    text = text.replace(
      /^(.*\\[a-zA-Z].*)$/gm,
      (_m: string, line: string) => {
        if (line.includes('$')) return _m;
        return `$${line.trim()}$`;
      }
    );
  }

  text = text.replace(/\n{3,}/g, '\n\n').trim();
  return text;
}

// ═══════════════════════════════════════════════════════════════════════
//  buildFullContent  — verbatim copy of the FIXED version from
//  crawler.controller.ts (sup→LaTeX, parseLeetCodeSamples w/ note,
//  ### 解释 #N template)
// ═══════════════════════════════════════════════════════════════════════
function buildFullContent(platform: string, record: any): string {
  const parts: string[] = [];
  if (record.background) parts.push(`[背景]\n${cleanMathJaxTriplication(record.background)}`);

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
  if (desc) parts.push(`[描述]\n${cleanMathJaxTriplication(desc)}`);

  if (record.constraints) parts.push(`[数据范围]\n${cleanMathJaxTriplication(record.constraints)}`);

  if (record.input_format && platform !== 'leetcode') parts.push(`[输入]\n${cleanMathJaxTriplication(record.input_format)}`);
  if (record.output_format && platform !== 'leetcode') parts.push(`[输出]\n${cleanMathJaxTriplication(record.output_format)}`);

  if (record.samples) {
    if (!Array.isArray(record.samples) && typeof record.samples === 'object' && record.samples !== null) {
      record.samples = Object.values(record.samples);
    }
    if (Array.isArray(record.samples) && record.samples.length > 0) {
      const sampleLines = record.samples.map((s: any, i: number) => {
        if (Array.isArray(s)) {
          return (
            `输入 #${i + 1}\n\`\`\`\n${s[0] || ''}\n\`\`\`\n\n` +
            `输出 #${i + 1}\n\`\`\`\n${s[1] || ''}\n\`\`\``
          );
        }
        return String(s);
      });
      parts.push(`[样例]\n${sampleLines.join('\n\n')}`);
    } else if (typeof record.samples === 'string' && record.samples.trim()) {
      parts.push(`[样例]\n${record.samples}`);
    }
  }

  if (record.hints && Array.isArray(record.hints) && record.hints.length > 0) {
    const hintText = record.hints.map((h: string, i: number) => `${i + 1}. ${h}`).join('\n');
    parts.push(`[提示]\n${hintText}`);
  } else if (record.hint) {
    parts.push(`[提示]\n${cleanMathJaxTriplication(record.hint)}`);
  }
  if (record.note) parts.push(`[注]\n${record.note}`);

  let description = record.content || record.description || '';
  if (description && description.trim().startsWith('<')) {
    if (platform === 'leetcode') {
      description = description.replace(
        /<pre>(?:<strong>)?\s*(?:Input|输入)\s*:?\s*(?:<\/strong>)?\s*[\s\S]*?\s*(?:<strong>)?\s*(?:Output|输出)\s*:?\s*(?:<\/strong>)?\s*[\s\S]*?\s*<\/pre>/gi,
        '',
      );
      description = description.replace(/<div[^>]*class="example-block"[^>]*>[\s\S]*?<\/div>/gi, '');
      description = description.replace(/<pre>[\s\S]*?<\/pre>/gi, '');
      description = description.replace(/<(?:strong|b)\s[^>]*class="example"[^>]*>.*?<\/(?:strong|b)>/gi, '');
      description = description.replace(/<(?:strong|b)>(?:提示|Note|Constraints)\s*:?\s*<\/(?:strong|b)>/gi, '');
    }
    // ── Step 1: <sup>/<sub> → inline LaTeX math ──
    description = description
      .replace(/([A-Za-z0-9.\-]+)<sup>([^<]+)<\/sup>/gi, (_m: string, p: string, x: string) => `$${p}^{${x}}$`)
      .replace(/([A-Za-z0-9.\-]+)<sub>([^<]+)<\/sub>/gi, (_m: string, p: string, x: string) => `$${p}_{${x}}$`);
    // ── Step 2: block-level tags → newlines ──
    description = description
      .replace(/<\/(?:p|div|li|h[1-6]|pre|blockquote|section|article|main|aside|header|footer|nav|figure|figcaption|details|summary|fieldset|form|table|tr|ul|ol|dl)>/gi, '\n')
      .replace(/<(?:br|hr)\b[^>]*\/?>/gi, '\n')
      .replace(/<\/?(?:p|div|h[1-6]|pre|blockquote|li|tr|ul|ol|dl|table|section|article|main|aside|header|footer|nav)\b[^>]*>/gi, '\n');
    // ── Step 3: strip remaining tags ──
    description = description.replace(/<[^>]+>/g, '');
    // ── Step 4: decode entities ──
    description = description
      .replace(/&#39;/g, "'").replace(/&#x27;/g, "'").replace(/&apos;/g, "'")
      .replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ')
      .replace(/&#8217;/g, "'").replace(/&#8216;/g, "'")
      .replace(/&#8220;/g, '"').replace(/&#8221;/g, '"')
      .replace(/&#8230;/g, '...').replace(/&#xA0;/g, ' ');
    // ── Step 5: whitespace normalisation ──
    description = description
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n[ \t]+/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  if (platform === 'leetcode') {
    const htmlContent = record.content || '';
    const parsedSamples = parseLeetCodeSamples(htmlContent);
    if (parsedSamples && parsedSamples.length > 0) {
      for (let i = parts.length - 1; i >= 0; i--) {
        if (parts[i].startsWith('[样例]')) parts.splice(i, 1);
      }
      const sampleLines = parsedSamples.map((s: any, i: number) => {
        if (Array.isArray(s)) {
          let block =
            `### 输入 #${i + 1}\n\`\`\`\n${s[0] || ''}\n\`\`\`\n\n` +
            `### 输出 #${i + 1}\n\`\`\`\n${s[1] || ''}\n\`\`\`\n`;
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
      const sampleTestCase = record.sampleTestCase || '';
      if (sampleTestCase) {
        parts.push(`[样例]\n输入 #1\n\`\`\`\n${sampleTestCase}\n\`\`\``);
      }
    }
  }

  if (description && !record.description) {
    parts.unshift(`[描述]\n${description}`);
  }
  return parts.length > 0 ? parts.join('\n\n') : (description || '');
}

// ═══════════════════════════════════════════════════════════════════════
//  Main
// ═══════════════════════════════════════════════════════════════════════
async function main(): Promise<void> {
  const problem = await prisma.problem.findUnique({
    where: { id: PROBLEM_ID },
    select: { id: true, sourcePlatform: true, sourceId: true, title: true, rawDetail: true, fullContent: true },
  });

  if (!problem) {
    console.error(`Problem ${PROBLEM_ID} not found`);
    process.exit(1);
  }
  if (problem.sourcePlatform !== 'leetcode') {
    console.error(`Expected leetcode, got ${problem.sourcePlatform}`);
    process.exit(1);
  }

  console.log(`Problem: id=${problem.id} source=${problem.sourcePlatform}/${problem.sourceId} title="${problem.title}"`);
  const before = problem.fullContent || '';
  console.log(`\n=== BEFORE (length=${before.length}) ===`);
  console.log(before);

  const newContent = buildFullContent('leetcode', problem.rawDetail as any);

  console.log(`\n=== AFTER (length=${newContent.length}) ===`);
  console.log(newContent);

  // Persist
  await prisma.problem.update({
    where: { id: PROBLEM_ID },
    data: { fullContent: newContent },
  });
  console.log(`\n[OK] full_content updated for ${PROBLEM_ID}`);
}

main()
  .catch(async (e) => {
    console.error('Fatal:', e);
    await prisma.$disconnect();
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
