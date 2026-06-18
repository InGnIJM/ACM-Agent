import { PrismaClient } from '@prisma/client';
import * as fs from 'fs';
import * as path from 'path';

const TARGET_UUID = '531a637b-0ac6-46b3-91ff-1837d20885c5';

/** Identical to CrawlerController.cleanMathJaxTriplication */
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
          const best = latexLines.reduce((a, b) => b.length > a.length ? b : a);
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

  if (!text.includes('$')) {
    text = text.replace(
      /^(.*\\[a-zA-Z].*)$/gm,
      (_m: string, line: string) => {
        if (line.includes('$')) return _m;
        return `$${line.trim()}$`;
      }
    );
  }

  text = text
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return text;
}

/** Match CrawlerController.buildFullContent for nowcoder platform */
function buildFullContent(record: any): string {
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

  if (record.input_format) parts.push(`[输入]\n${cleanMathJaxTriplication(record.input_format)}`);
  if (record.output_format) parts.push(`[输出]\n${cleanMathJaxTriplication(record.output_format)}`);

  if (record.samples) {
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
    }
  }

  if (record.hints && Array.isArray(record.hints) && record.hints.length > 0) {
    const hintText = record.hints.map((h: string, i: number) => `${i + 1}. ${h}`).join('\n');
    parts.push(`[提示]\n${hintText}`);
  } else if (record.hint) {
    parts.push(`[提示]\n${cleanMathJaxTriplication(record.hint)}`);
  }

  if (record.note) parts.push(`[注]\n${record.note}`);

  return parts.length > 0 ? parts.join('\n\n') : '';
}

async function main() {
  const p = new PrismaClient();
  try {
    const rawPath = path.resolve(__dirname, '../../python/data/raw/nowcoder/problems/2026-06-18_318732.json');
    const raw = JSON.parse(fs.readFileSync(rawPath, 'utf-8'));

    console.log('Title:', raw.title);
    console.log('Desc length:', (raw.description || '').length);
    console.log('Samples:', raw.samples?.length);

    const fullContent = buildFullContent(raw);
    console.log('fullContent length:', fullContent.length);
    console.log('Has math formulas ($):', fullContent.includes('$'));

    // Update by UUID directly
    const existing = await p.problem.findUnique({
      where: { id: TARGET_UUID }
    });

    if (!existing) {
      console.error('ERROR: Problem with UUID', TARGET_UUID, 'not found');
      process.exit(1);
    }

    console.log('Existing problem:', existing.id, existing.title, existing.sourcePlatform, existing.sourceId);

    await p.problem.update({
      where: { id: TARGET_UUID },
      data: {
        title: raw.title,
        fullContent: fullContent,
        rawDetail: raw,
        difficultyRaw: raw.difficulty || null,
      }
    });

    console.log('Updated:', TARGET_UUID);

    // Verify
    const verify = await p.problem.findUnique({
      where: { id: TARGET_UUID }
    });
    console.log('Verify fc length:', verify?.fullContent?.length || 0);
    console.log('Verify has math ($):', verify?.fullContent?.includes('$') || false);
    console.log('Done!');
  } catch (e: any) {
    console.error('ERROR:', e.message || e);
  }
  await p.$disconnect();
}

main();
