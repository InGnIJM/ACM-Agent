/**
 * Standalone script: import crawled problem JSON files into the database.
 *
 * Reads saved problem JSON files from data/raw/{platform}/problems/
 * and upserts them via Prisma.  Reuses the same logic as
 * CrawlerController.upsertProblem() + buildFullContent().
 *
 * Usage:
 *   npx tsx src/crawler/import-problems.ts <platform>
 *   npx tsx src/crawler/import-problems.ts leetcode
 *
 * Platforms: leetcode, codeforces, nowcoder, atcoder, luogu
 */

import { PrismaClient } from '@prisma/client';
import * as fs from 'fs';
import * as path from 'path';

const prisma = new PrismaClient();

const DATA_DIR = path.resolve(__dirname, '../../../python/data/raw');

// ═══════════════════════════════════════════════════
//  Difficulty normalisation (mirrors CrawlerController)
// ═══════════════════════════════════════════════════
function normalizeDifficulty(platform: string, raw: string | null): number {
  if (raw === null || raw === undefined) return 1500;
  const s = String(raw).trim().toLowerCase();
  const lcMap: Record<string, number> = { easy: 900, medium: 1700, hard: 2500 };
  if (platform === 'leetcode' && lcMap[s] != null) return lcMap[s];
  const lgMap: Record<string, number> = {
    '1': 600, '2': 1000, '3': 1400, '4': 1800, '5': 2200, '6': 2700, '7': 3200,
  };
  if (platform === 'luogu' && lgMap[s] != null) return lgMap[s];
  const ncMap: Record<string, number> = {
    '入门': 600, '简单': 1000, '中等': 1700, '较难': 2200, '困难': 2800,
  };
  if (platform === 'nowcoder' && ncMap[raw] != null) return ncMap[raw];
  const num = Number(raw);
  if (!isNaN(num)) {
    if (platform === 'atcoder') return Math.min(num, 3500);
    return num;
  }
  return 1500;
}

// ═══════════════════════════════════════════════════
//  HTML → plain text
// ═══════════════════════════════════════════════════
function htmlToPlainText(html: string): string {
  return html
    .replace(/<sup>([^<]*)<\/sup>/gi, '^$1')
    .replace(/<\/(?:p|div|li|h[1-6]|pre|blockquote|section|article|main|aside|header|footer|nav|figure|figcaption|details|summary|fieldset|form|table|tr|ul|ol|dl)>/gi, '\n')
    .replace(/<(?:br|hr)\b[^>]*\/?>/gi, '\n')
    .replace(/<\/?(?:p|div|h[1-6]|pre|blockquote|li|tr|ul|ol|dl|table|section|article|main|aside|header|footer|nav)\b[^>]*>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&#39;/g, "'").replace(/&#x27;/g, "'").replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&').replace(/&nbsp;/g, ' ')
    .replace(/&#8217;/g, "'").replace(/&#8216;/g, "'")
    .replace(/&#8220;/g, '"').replace(/&#8221;/g, '"')
    .replace(/&#8230;/g, '...').replace(/&#xA0;/g, ' ')
    .replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n')
    .replace(/\n{3,}/g, '\n\n').trim();
}

// ═══════════════════════════════════════════════════
//  LeetCode sample parser (supports Chinese labels)
// ═══════════════════════════════════════════════════
function parseLeetCodeSamples(html: string): Array<[string, string]> | null {
  if (!html) return null;
  const pairs: Array<[string, string]> = [];

  // Pass 1: old <pre> format
  const preRegex = /<pre>(?:<strong>)?\s*(?:Input|输入)\s*:?\s*(?:<\/strong>)?\s*([\s\S]*?)\s*(?:<strong>)?\s*(?:Output|输出)\s*:?\s*(?:<\/strong>)?\s*([\s\S]*?)\s*<\/pre>/gi;
  let match: RegExpExecArray | null;
  while ((match = preRegex.exec(html)) !== null) {
    let input = (match[1] || '').replace(/<[^>]+>/g, '').trim();
    let output = (match[2] || '').replace(/<[^>]+>/g, '').trim();
    output = output.replace(/\n\s*(?:<strong>)?\s*(?:Explanation|解释)\s*:?[\s\S]*$/i, '').trim();
    output = output.replace(/\n\s*(?:<strong>)?\s*(?:Note|提示)\s*:?[\s\S]*$/i, '').trim();
    if (input || output) pairs.push([input, output]);
  }

  // Pass 2: new <div class="example-block"> format (LeetCode CN current)
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

// ═══════════════════════════════════════════════════
//  buildFullContent (mirrors CrawlerController)
// ═══════════════════════════════════════════════════
function buildFullContent(platform: string, record: any): string {
  const parts: string[] = [];

  // Structured sections from crawl output
  const limitsHeader = record.limits
    ? `时间限制：${record.limits.time || '?'} ms / 空间限制：${record.limits.memory || '?'} MB`
    : '';
  if (record.background) parts.push(`[背景]\n${record.background}`);
  if (record.description) {
    parts.push(`[描述]\n${limitsHeader ? limitsHeader + '\n\n' : ''}${record.description}`);
  }
  if (record.constraints) parts.push(`[数据范围]\n${record.constraints}`);
  if (record.input_format && platform !== 'leetcode') parts.push(`[输入]\n${record.input_format}`);
  if (record.output_format && platform !== 'leetcode') parts.push(`[输出]\n${record.output_format}`);

  // Samples from crawl output (non-LeetCode)
  const samplesData = record.samples;
  if (samplesData && Array.isArray(samplesData) && samplesData.length > 0) {
    const sampleLines = samplesData.map((s: any, i: number) => {
      if (Array.isArray(s)) {
        return `输入 #${i + 1}\n\`\`\`\n${s[0] || ''}\n\`\`\`\n\n输出 #${i + 1}\n\`\`\`\n${s[1] || ''}\n\`\`\``;
      }
      return String(s);
    });
    parts.push(`[样例]\n${sampleLines.join('\n\n')}`);
  }

  // HTML content → plain text (LeetCode)
  let description = record.content || '';
  if (description && description.trim().startsWith('<')) {
    if (platform === 'leetcode') {
      // Remove old-format <pre> example blocks
      description = description.replace(
        /<pre>(?:<strong>)?\s*(?:Input|输入)\s*:?\s*(?:<\/strong>)?\s*[\s\S]*?\s*(?:<strong>)?\s*(?:Output|输出)\s*:?\s*(?:<\/strong>)?\s*[\s\S]*?\s*<\/pre>/gi,
        '',
      );
      // Remove new-format <div class="example-block"> entirely
      description = description.replace(
        /<div[^>]*class="example-block"[^>]*>[\s\S]*?<\/div>/gi,
        '',
      );
      // Remove orphaned <pre> explanation blocks (new format leftovers)
      description = description.replace(
        /<pre>[\s\S]*?<\/pre>/gi,
        '',
      );
      // Remove orphaned example/tip label elements outside example-block
      // e.g. <strong class="example">示例 1：</strong>
      description = description.replace(
        /<(?:strong|b)\s[^>]*class="example"[^>]*>.*?<\/(?:strong|b)>/gi,
        '',
      );
      description = description.replace(
        /<(?:strong|b)>(?:提示|Note|Constraints)\s*:?\s*<\/(?:strong|b)>/gi,
        '',
      );
    }
    description = htmlToPlainText(description);
  }

  // LeetCode: parse samples from HTML content
  if (platform === 'leetcode') {
    const htmlContent = record.content || '';
    const parsedSamples = parseLeetCodeSamples(htmlContent);
    if (parsedSamples && parsedSamples.length > 0) {
      for (let i = parts.length - 1; i >= 0; i--) {
        if (parts[i].startsWith('[样例]')) parts.splice(i, 1);
      }
      const sampleLines = parsedSamples.map((s, i) =>
        `输入 #${i + 1}\n\`\`\`\n${s[0] || ''}\n\`\`\`\n\n输出 #${i + 1}\n\`\`\`\n${s[1] || ''}\n\`\`\``,
      );
      parts.push(`[样例]\n${sampleLines.join('\n\n')}`);
    } else {
      const sampleTestCase = (record as any).sampleTestCase || '';
      if (sampleTestCase) {
        parts.push(`[样例]\n输入 #1\n\`\`\`\n${sampleTestCase}\n\`\`\``);
      }
    }
    // For LeetCode, description goes FIRST (before samples)
    if (description) parts.unshift(`[描述]\n${description}`);
  } else if (description && !record.description) {
    // For other platforms, description goes first (replaces structured description if missing)
    parts.unshift(`[描述]\n${description}`);
  }

  // Hints + notes
  if (record.hints && Array.isArray(record.hints) && record.hints.length > 0) {
    parts.push(`[提示]\n${record.hints.map((h: string, i: number) => `${i + 1}. ${h}`).join('\n')}`);
  } else if (record.hint) {
    parts.push(`[提示]\n${record.hint}`);
  }
  if (record.note) parts.push(`[注]\n${record.note}`);

  return parts.join('\n\n');
}

// ═══════════════════════════════════════════════════
//  Source URL builder
// ═══════════════════════════════════════════════════
function buildSourceUrl(platform: string, record: any, sourceId: string): string | null {
  if (record.source_url) return record.source_url;
  const sid = String(sourceId);
  switch (platform) {
    case 'luogu':
      return `https://www.luogu.com.cn/problem/${sid}`;
    case 'codeforces': {
      const cid = record.contestId || '';
      const idx = record.index || '';
      return cid && idx ? `https://codeforces.com/problemset/problem/${cid}/${idx}` : null;
    }
    case 'leetcode': {
      const slug = record.titleSlug || record.slug || '';
      return slug ? `https://leetcode.cn/problems/${slug}/` : null;
    }
    case 'nowcoder':
      return `https://ac.nowcoder.com/acm/problem/${sid}`;
    case 'atcoder': {
      const cid = record.contest_id || record.contestId || '';
      return cid ? `https://atcoder.jp/contests/${cid}/tasks/${sid}` : null;
    }
    default:
      return null;
  }
}

// ═══════════════════════════════════════════════════
//  Import one problem JSON file
// ═══════════════════════════════════════════════════
async function importOne(platform: string, filePath: string): Promise<boolean> {
  const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  const record = raw.data ?? raw; // some crawlers wrap in {success, data}

  // Determine sourceId
  const cfId = record.contestId && record.index ? `${record.contestId}${record.index}` : null;
  const sourceId =
    record.source_id || record.pid || record.id || cfId ||
    record.questionId || record.questionFrontendId || record.titleSlug;
  if (!sourceId) {
    console.log(`  SKIP ${path.basename(filePath)}: no sourceId`);
    return false;
  }

  const rawDifficulty =
    record.difficulty != null ? String(record.difficulty)
    : record.difficulty_raw != null ? String(record.difficulty_raw)
    : record.difficultyRaw != null ? String(record.difficultyRaw)
    : record.rating != null ? String(record.rating)
    : null;

  const rawTags = record.tags || record.topicTags || [];
  const tagsNormalized: string[] = Array.isArray(rawTags)
    ? rawTags.map((t: any) => (typeof t === 'string' ? t : t?.name || t?.slug || String(t)))
    : [];
  const tagsPlatformSafe = Array.isArray(rawTags) ? rawTags : [];
  const normalizedDiff = normalizeDifficulty(platform, rawDifficulty);
  const fullContent = buildFullContent(platform, record);
  const sourceUrl = buildSourceUrl(platform, record, sourceId);

  // Hard-delete any soft-deleted record first (bypasses Prisma middleware)
  await prisma.$executeRawUnsafe(
    `DELETE FROM "problems" WHERE "source_platform" = $1::"Platform" AND "source_id" = $2 AND "deleted_at" IS NOT NULL`,
    platform,
    String(sourceId),
  );

  await prisma.problem.upsert({
    where: {
      sourcePlatform_sourceId: {
        sourcePlatform: platform as any,
        sourceId: String(sourceId),
      },
    },
    create: {
      sourcePlatform: platform as any,
      sourceId: String(sourceId),
      sourceUrl,
      title: record.title || record.name || '',
      difficultyRaw: rawDifficulty,
      difficultyNormalized: normalizedDiff,
      tagsNormalized,
      tagsPlatform: tagsPlatformSafe,
      rawDetail: record,
      fullContent,
    },
    update: {
      sourceUrl,
      title: record.title || record.name || '',
      difficultyRaw: rawDifficulty,
      difficultyNormalized: normalizedDiff,
      tagsNormalized,
      tagsPlatform: tagsPlatformSafe,
      rawDetail: record,
      fullContent,
    },
  });

  const title = record.title || record.name || '?';
  console.log(`  OK  ${platform}/${sourceId}  "${title.slice(0, 60)}"`);
  return true;
}

// ═══════════════════════════════════════════════════
//  Main
// ═══════════════════════════════════════════════════
async function main(): Promise<void> {
  const platform = process.argv[2];
  if (!platform || !['leetcode', 'codeforces', 'nowcoder', 'atcoder', 'luogu'].includes(platform)) {
    console.error('Usage: npx tsx src/crawler/import-problems.ts <platform>');
    process.exit(1);
  }

  const problemsDir = path.join(DATA_DIR, platform, 'problems');
  if (!fs.existsSync(problemsDir)) {
    console.error(`Directory not found: ${problemsDir}`);
    process.exit(1);
  }

  const files = fs
    .readdirSync(problemsDir)
    .filter((f) => f.endsWith('.json') && !f.startsWith('bulk_'));

  if (files.length === 0) {
    console.log(`No problem files for ${platform}`);
    process.exit(0);
  }

  console.log(`Importing ${files.length} files for ${platform}...\n`);

  let ok = 0;
  let fail = 0;
  for (const f of files) {
    try {
      const success = await importOne(platform, path.join(problemsDir, f));
      if (success) ok++;
      else fail++;
    } catch (err: any) {
      console.error(`  FAIL ${f}: ${err?.message || err}`);
      fail++;
    }
  }

  console.log(`\nDone: ${ok} ok, ${fail} failed`);
}

main()
  .catch(async (e) => {
    console.error('Fatal:', e);
    await prisma.$disconnect();
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
