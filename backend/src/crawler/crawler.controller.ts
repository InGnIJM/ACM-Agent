import {
  Controller,
  Post,
  Get,
  Body,
  Param,
  Query,
  UseGuards,
  HttpCode,
  ConflictException,
  NotFoundException,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import * as fs from 'fs';
import * as path from 'path';
import { PythonService } from './python.service';
import { TriggerCrawlDto } from './dto/trigger-crawl.dto';
import { BulkCrawlDto } from './dto/bulk-crawl.dto';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { Logger } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { VectorService } from '../common/vector/vector.service';
import {
  buildFullContent as buildFullContentUtil,
} from './fullcontent.util';

@ApiTags('Crawler')
@ApiBearerAuth()
@Controller('api/crawler')
export class CrawlerController {
  private readonly logger = new Logger(CrawlerController.name);
  private readonly dataDir = path.resolve(__dirname, '../../../python/data/raw');

  private readonly platformScripts: Record<string, string> = {
    luogu: 'crawlers/luogu.py',
    leetcode: 'crawlers/leetcode.py',
    codeforces: 'crawlers/codeforces.py',
    atcoder: 'crawlers/atcoder.py',
    nowcoder: 'crawlers/nowcoder.py',
  };

  private readonly loginScripts: Record<string, string> = {
    luogu: 'crawlers/luogu_login.py',
    leetcode: 'crawlers/leetcode_login.py',
    codeforces: 'crawlers/codeforces_login.py',
    atcoder: 'crawlers/atcoder_login.py',
    nowcoder: 'crawlers/nowcoder_login.py',
  };

  constructor(
    private readonly pythonService: PythonService,
    private readonly prisma: PrismaService,
    private readonly vectorService: VectorService,
  ) {}

  @Post('trigger/user/:userId')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Trigger single user crawl' })
  async triggerUserCrawl(@Param('userId') userId: string): Promise<{ accepted: boolean; userId: string }> {
    this.logger.log(`Triggering crawl for user: ${userId}`);
    // Fire-and-forget: do not await to avoid blocking the HTTP response
    this.pythonService
      .execute('crawlers/user_crawler.py', { userId })
      .catch((err) => this.logger.error(`User crawl failed for ${userId}: ${err.message}`));
    return { accepted: true, userId };
  }

  @Post('trigger/all')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Trigger crawl for all observed users' })
  async triggerAllUsers(): Promise<{ accepted: boolean }> {
    this.logger.log('Triggering crawl for all observed users');
    this.pythonService
      .execute('crawlers/user_crawler.py', { all: true })
      .catch((err) => this.logger.error(`All-users crawl failed: ${err.message}`));
    return { accepted: true };
  }

  @Post('trigger/problems')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(200)
  @ApiOperation({ summary: 'Trigger crawl task (problems, user, records, solutions, import)' })
  async triggerProblemCrawl(@Body() dto: TriggerCrawlDto): Promise<{ success: boolean; platform?: string; action?: string; imported?: number; importedDetail?: { problems: number; solutions: number; records: number; total: number }; count?: number; titles?: string; embedJobId?: string | null }> {
    this.logger.log(`Triggering crawl: platform=${dto.platform || 'all'}, action=${dto.action}, uid=${dto.uid || 'none'}, tags=${dto.tags || 'none'}, count=${dto.count ?? 50}`);

    // Map platform to its crawler script
    const script = dto.platform ? this.platformScripts[dto.platform] : null;
    if (!script) {
      this.logger.warn(`Unknown or missing platform: ${dto.platform}`);
      return { success: false, platform: dto.platform, action: dto.action };
    }

    // Query existing sourceIds so Python can skip already-imported problems
    let skipIds: string[] = [];
    if (dto.action === 'fetch_problems' && dto.platform) {
      try {
        const existing = await this.prisma.$queryRaw<Array<{sourceId: string}>>`
          SELECT "source_id" as "sourceId" FROM "problems"
            WHERE "source_platform" = ${dto.platform}::"Platform"
              AND "deleted_at" IS NULL
        `;
        skipIds = existing.map((p) => p.sourceId);
        this.logger.log(`Skip ${skipIds.length} already-imported problem IDs for ${dto.platform}`);
      } catch (err: any) {
        this.logger.warn(`Failed to query existing problems: ${err?.message || err}`);
      }
    }

    // Pass all params as JSON via --input (same format all platform CLIs expect)
    const params = {
      action: dto.action,
      uid: dto.uid,
      tags: dto.tags,
      count: dto.count ?? 50,
      skip_ids: skipIds,
    };

    // Await Python execution so we can return problem names
    try {
      const result: any = await this.pythonService.execute(script, params);
      this.logger.log(`Crawl completed for ${dto.platform}: success=${result?.success}, dataCount=${Array.isArray(result?.data) ? result.data.length : 'N/A'}`);

      const dataList = Array.isArray(result?.data) ? result.data : [];
      let titles = '';
      if (result?.success && dataList.length > 0) {
        titles = dataList.slice(0, 20).map((p: any) => p.name || p.title || p.pid || '?').join(', ');
        this.logger.log(`Fetched ${dataList.length} problems: ${titles}`);
      }

      // Auto-import: import all files in the platform directory.
      // The Python crawler overwrites existing files, so "new file" detection
      // by file existence does not work.  upsert handles duplicates safely.
      let importDetail = { problems: 0, solutions: 0, records: 0, total: 0, problemSourceIds: [] as string[] };
      let embedJobId: string | null = null;
      if (result?.success && dto.platform) {
        try {
          importDetail = await this.importPlatformData(dto.platform);
          this.logger.log(`Import completed for ${dto.platform}: ${importDetail.total} records upserted (${importDetail.problems} problems, ${importDetail.solutions} solutions, ${importDetail.records} records)`);

          // Only auto-summarize if DeepSeek (official or Alibaba Cloud) API key is configured
          const hasApiKey = this.resolveDeepSeekConfig() !== null;
          if (importDetail.total > 0 && hasApiKey) {
            const embedJob = await this.prisma.crawlJob.create({
              data: {
                platform: dto.platform as any,
                status: 'running',
                phase: 'import_',
                config: { type: 'embed', sourceAction: dto.action, imported: importDetail.total },
                startedAt: new Date(),
              },
            });
            embedJobId = embedJob.id;
            this.summarizeUnprocessed(dto.platform, embedJob.id, importDetail.problemSourceIds)
              .then(async (r) => {
                this.logger.log(`Auto-summarize done for ${dto.platform}: ${r.embedded} summarized, ${r.skipped} skipped`);
                await this.prisma.crawlJob.update({
                  where: { id: embedJob.id },
                  data: { status: 'completed', finishedAt: new Date(), summary: { embedded: r.embedded, skipped: r.skipped } },
                }).catch(() => {});
              })
              .catch(async (err) => {
                this.logger.error(`Auto-summarize failed: ${err?.message || err}`);
                await this.prisma.crawlJob.update({
                  where: { id: embedJob.id },
                  data: { status: 'failed', finishedAt: new Date() },
                }).catch(() => {});
              });
          }
        } catch (err: any) {
          this.logger.error(`Import failed for ${dto.platform}: ${err?.message || err}`);
        }
      }

      return {
        success: true,
        platform: dto.platform,
        action: dto.action,
        count: dataList.length,
        imported: importDetail.total,
        importedDetail: importDetail,
        embedJobId,
        titles: titles || undefined,
      };
    } catch (err: any) {
      this.logger.error(`Crawl failed for ${dto.platform}: ${err.message}`);
      return { success: false, platform: dto.platform, action: dto.action };
    }
  }

  /** Read JSON files from data/raw/{platform}/{subDir}/ and upsert to database. */
  private async importPlatformData(platform: string): Promise<{ problems: number; solutions: number; records: number; total: number; problemSourceIds: string[] }> {
    const platformDir = path.join(this.dataDir, platform);
    this.logger.log(`[IMPORT] platform=${platform} dataDir=${this.dataDir} platformDir=${platformDir}`);
    if (!fs.existsSync(platformDir)) {
      this.logger.warn(`[IMPORT] No data directory for platform ${platform}: ${platformDir}`);
      return { problems: 0, solutions: 0, records: 0, total: 0, problemSourceIds: [] };
    }

    let problems = 0;
    let solutions = 0;
    let recordsCount = 0;
    const problemSourceIds: string[] = [];
    const subDirs = ['problems', 'profiles', 'records', 'solutions'];

    for (const subDir of subDirs) {
      const dir = path.join(platformDir, subDir);
      if (!fs.existsSync(dir)) {
        this.logger.log(`[IMPORT]   subDir ${subDir}: does not exist, skip`);
        continue;
      }

      const files = fs.readdirSync(dir).filter((f) => f.endsWith('.json') && !f.startsWith('bulk_list_') && !f.startsWith('bulk_detail_progress_'));
      this.logger.log(`[IMPORT]   subDir ${subDir}: ${files.length} files`);
      if (files.length === 0) continue;

      for (const file of files) {
        const filePath = path.join(dir, file);

        try {
          const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
          const records = Array.isArray(raw) ? raw : [raw];
          this.logger.log(`[IMPORT]     file=${file} records=${records.length}`);

          // Extract sourceId from filename: {date}_{sourceId}.json
          const fileSourceId = file.replace(/^\d{4}-\d{2}-\d{2}_/, '').replace('.json', '');

          for (const record of records) {
            if (subDir === 'problems') {
              // Match the fallback chain in upsertProblem() (line 267-271)
              // so problemSourceIds is never empty for valid records.
              const cfId = record.contestId && record.index ? `${record.contestId}${record.index}` : null;
              const sid = platform === 'leetcode'
                ? (record.titleSlug || record.slug || record.questionId || record.questionFrontendId)
                : (record.source_id || record.sourceId || record.pid || record.id || cfId);
              this.logger.log(`[IMPORT]       upsertProblem: sourceId=${sid} title=${(record.title || record.name || '?').slice(0, 30)}`);
              await this.upsertProblem(platform, record);
              problems++;
              if (sid) problemSourceIds.push(String(sid));
            } else if (subDir === 'records') {
              await this.upsertRecord(platform, record);
              recordsCount++;
            } else if (subDir === 'solutions') {
              await this.upsertSolutions(platform, record, fileSourceId);
              solutions++;
            }
          }
          // Remove processed file to avoid re-import
          fs.unlinkSync(filePath);
          this.logger.log(`[IMPORT]     file=${file} done, deleted`);
        } catch (err: any) {
          this.logger.warn(`[IMPORT]     FAILED file=${file}: ${err?.message || err}`);
        }
      }
    }

    const total = problems + solutions + recordsCount;
    this.logger.log(`[IMPORT] DONE: problems=${problems} solutions=${solutions} records=${recordsCount} total=${total}`);
    return { problems, solutions, records: recordsCount, total, problemSourceIds };
  }

  private async upsertProblem(platform: string, record: any): Promise<void> {
    // Codeforces: construct sourceId from contestId+index (e.g. "2236C")
    const cfId = record.contestId && record.index ? `${record.contestId}${record.index}` : null;
    // LeetCode: prefer titleSlug (natural identifier, matches solution filenames)
    let sourceId = platform === 'leetcode'
      ? (record.titleSlug || record.slug || record.questionId || record.questionFrontendId || record.source_id || record.sourceId || record.pid || record.id)
      : (record.source_id || record.sourceId || record.pid || record.id || cfId || record.titleSlug || record.questionId || record.questionFrontendId);
    // Truncate to VARCHAR(50) limit
    if (sourceId && sourceId.length > 50) {
      sourceId = sourceId.slice(0, 50);
    }
    if (!sourceId) return;

    const rawDifficulty = record.difficulty != null ? String(record.difficulty)
      : (record.difficulty_raw != null ? String(record.difficulty_raw)
      : (record.difficultyRaw != null ? String(record.difficultyRaw)
      : (record.rating != null ? String(record.rating) : null)));
    if (!rawDifficulty) {
      this.logger.warn(`Missing difficulty for ${platform}/${sourceId} — defaulting to 1500`);
    }
    // Support both flat tag arrays (tags) and LeetCode-style topicTags [{name,slug}]
    const rawTags = record.tags || record.topicTags || [];
    const tagsNormalized = Array.isArray(rawTags)
      ? rawTags.map((t: any) => (typeof t === 'string' ? t : t?.name || t?.slug || String(t)))
      : [];
    const tagsPlatformSafe = Array.isArray(rawTags) ? rawTags : [];
    const normalizedDiff = this.normalizeDifficulty(platform, rawDifficulty);

    const fullContent = this.buildFullContent(platform, record);

    // Generate platform source URL
    let sourceUrl: string | null = record.source_url || record.sourceUrl || null;
    if (!sourceUrl) {
      const sid = String(sourceId);
      if (platform === 'luogu') {
        sourceUrl = `https://www.luogu.com.cn/problem/${sid}`;
      } else if (platform === 'codeforces') {
        const cid = record.contestId || '';
        const idx = record.index || '';
        if (cid && idx) sourceUrl = `https://codeforces.com/problemset/problem/${cid}/${idx}`;
      } else if (platform === 'leetcode') {
        const slug = record.titleSlug || record.slug || '';
        if (slug) sourceUrl = `https://leetcode.cn/problems/${slug}/`;
      } else if (platform === 'nowcoder') {
        sourceUrl = `https://ac.nowcoder.com/acm/problem/${sid}`;
      } else if (platform === 'atcoder') {
        const cid = record.contest_id || record.contestId || '';
        if (cid) sourceUrl = `https://atcoder.jp/contests/${cid}/tasks/${sid}`;
        else sourceUrl = `https://atcoder.jp/contests/${sid}/tasks/${sid}`;
      }
    }

    // Fix: Prisma middleware auto-adds `deletedAt: null` to findUnique,
    // which prevents upsert from finding soft-deleted records, causing
    // unique-constraint violations.  Hard-delete any soft-deleted record
    // first so upsert can cleanly create or update.
    try {
      await this.prisma.$executeRaw`
        DELETE FROM "problems"
        WHERE "source_platform" = ${platform}::"Platform"
          AND "source_id" = ${String(sourceId)}
          AND "deleted_at" IS NOT NULL
      `;
    } catch (_) {
      // Record may not exist or may not be soft-deleted — ignore
    }

    await this.prisma.problem.upsert({
      where: {
        sourcePlatform_sourceId: { sourcePlatform: platform as any, sourceId: String(sourceId) },
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
        deletedAt: null,
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
        deletedAt: null,  // defensive: ensure re-imported records are un-deleted
      },
    });
  }

  private async upsertSolutions(platform: string, record: any, sourceIdHint?: string): Promise<void> {
    // record is a list of solutions from fetch_solutions output
    const solutions = Array.isArray(record) ? record : [record];
    for (const sol of solutions) {
      const author = sol.author || '匿名';
      const content = sol.content || '';
      if (!content) continue;
      // Find the problem this solution belongs to
      const sourceId = sol.problem_id || sol.pid || sourceIdHint;
      if (!sourceId) continue;
      let problem = await this.prisma.problem.findUnique({
        where: { sourcePlatform_sourceId: { sourcePlatform: platform as any, sourceId: String(sourceId) } },
        select: { id: true },
      });
      // Fallback for LeetCode: sourceIdHint is titleSlug, but problem.sourceId may be questionId
      // or a truncated version of the slug (VARCHAR(50) limit)
      if (!problem && platform === 'leetcode' && sourceIdHint) {
        const allLc = await this.prisma.problem.findMany({
          where: { sourcePlatform: 'leetcode' as any },
          select: { id: true, rawDetail: true },
        });
        for (const p of allLc) {
          const detail = (p.rawDetail || {}) as any;
          const slug = detail.titleSlug || detail.slug || '';
          if (slug === sourceIdHint || slug.slice(0, 50) === sourceIdHint) {
            problem = { id: p.id };
            break;
          }
        }
      }
      if (!problem) continue;

      // Determine solutionIndex:
      // - Codeforces: each problem has exactly ONE editorial → always use 0.
      //   This guarantees upsert updates the same row across re-crawls,
      //   preventing duplicates when the crawling logic changes.
      // - Other platforms: use content-fingerprint hash so re-crawling the
      //   same content maps to the same row.
      let solutionIndex: number;
      if (platform === 'codeforces' && sol.solution_index !== undefined) {
        solutionIndex = Number(sol.solution_index) % 100000;
      } else if (platform === 'codeforces') {
        solutionIndex = 0;
      } else {
        const contentFingerprint = content.slice(0, 200);
        let hash = 0;
        for (let i = 0; i < contentFingerprint.length; i++) {
          hash = ((hash << 5) - hash + contentFingerprint.charCodeAt(i)) | 0;
        }
        solutionIndex = Math.abs(hash) % 100000;
      }

      // For Codeforces: ensure exactly one solution per problem by cleaning
      // up old rows created with different content hashes from previous crawl
      // logic versions.
      if (platform === 'codeforces') {
        await this.prisma.problemSolution.deleteMany({
          where: {
            problemId: problem.id,
            solutionIndex: { not: solutionIndex },
          },
        });
      }

      await this.prisma.problemSolution.upsert({
        where: {
          problemId_solutionIndex: { problemId: problem.id, solutionIndex },
        },
        create: {
          problemId: problem.id,
          solutionIndex,
          content,
          author: String(author),
        },
        update: {
          content,
          author: String(author),
        },
      });
      // Note: solution vectors are no longer stored — only problem.solution_summary is vectorized.
    }
  }

  /** Map platform-specific difficulty to a unified 0–3500 rating scale.
   *
   *  Based on real OJ rating mechanisms:
   *
   *  Luogu 1-7 (入门→NOI) + score 1-100:
   *    1(入门)    → 600      2(普及−)     → 1000     3(普及、提高−) → 1400
   *    4(普及+、提高) → 1800  5(提高+、省选−) → 2200    6(省选、NOI−)  → 2700
   *    7(NOI/NOI+) → 3200
   *
   *  Codeforces 800-3500:  native rating, used directly
   *  AtCoder 0-4000+:       native rating, used directly
   *  LeetCode E/M/H:       Easy→900  Medium→1700  Hard→2500
   *  NowCoder 入门/简单/中等/较难/困难:  same as Luogu 1-5
   */
  private normalizeDifficulty(platform: string, raw: string | null): number {
    if (!raw) return 1500;

    const num = Number(raw);

    if (platform === 'luogu') {
      // Luogu difficulty: 1-7 level OR 1-100 internal score
      if (!isNaN(num)) {
        // Difficulty 0 means "暂无评定" (not yet rated) — use universal default
        if (num <= 0) return 1500;
        // Integer 1-7 → direct level mapping
        if (Number.isInteger(num) && num >= 1 && num <= 7) {
          const mapping: Record<number, number> = { 1: 600, 2: 1000, 3: 1400, 4: 1800, 5: 2200, 6: 2700, 7: 3200 };
          return mapping[num];
        }
        // Internal scoring 1-100 (from user voting, non-integer or >7)
        if (num <= 5) return 600;
        if (num <= 12) return 1000;
        if (num <= 20) return 1400;
        if (num <= 35) return 1800;
        if (num <= 45) return 2200;
        if (num <= 70) return 2700;
        return 3200;
      }
      return 1500;
    }

    if (platform === 'nowcoder') {
      // 5 text levels: 入门/简单/中等/较难/困难
      const s = (raw || '').toLowerCase();
      if (s === '入门' || s === 'entry') return 600;
      if (s === '简单' || s === 'easy') return 1000;
      if (s === '中等' || s === 'medium') return 1700;
      if (s === '较难' || s === 'hard') return 2200;
      if (s === '困难' || s === 'very_hard') return 2800;
      if (!isNaN(num)) {
        // Numeric rating (e.g. 1500, 1900, 2400) vs level index (1-5)
        if (num > 5) {
          // Rating scale: typically 500–2500, clamp to 0-3500
          return Math.min(3500, Math.max(0, Math.round(num)));
        }
        if (num <= 1) return 600;
        if (num === 2) return 1000;
        if (num === 3) return 1700;
        if (num === 4) return 2200;
        return 2800; // num === 5
      }
      return 1500;
    }

    if (platform === 'codeforces') {
      // Native rating 800-3500
      if (!isNaN(num)) return Math.min(3500, Math.max(0, Math.round(num)));
      return 1500;
    }

    if (platform === 'atcoder') {
      // Native rating 0-4000+
      if (!isNaN(num)) return Math.min(3500, Math.max(0, Math.round(num)));
      return 1500;
    }

    if (platform === 'leetcode') {
      const s = (raw || '').toLowerCase();
      if (s === 'easy') return 900;
      if (s === 'medium') return 1700;
      if (s === 'hard') return 2500;
      if (!isNaN(num)) {
        if (num <= 1) return 900;
        if (num === 2) return 1700;
        return 2500;
      }
      return 1500;
    }

    if (!isNaN(num)) return Math.min(3500, Math.max(0, Math.round(num)));
    return 1500;
  }

  private async upsertRecord(platform: string, record: any): Promise<void> {
    const submissionId = record.id || record.record_id || record.platform_submission_id || `${record.uid}_${record.timestamp}`;
    if (!submissionId) return;

    await this.prisma.practiceRecord.upsert({
      where: {
        platform_platformSubmissionId: { platform: platform as any, platformSubmissionId: String(submissionId) },
      },
      create: {
        platform: platform as any,
        userId: '00000000-0000-0000-0000-000000000000', // placeholder — needs real userId mapping
        problemId: '00000000-0000-0000-0000-000000000000', // placeholder — needs real problemId mapping
        platformSubmissionId: String(submissionId),
        submitTime: record.timestamp || record.submit_time || new Date(),
        verdict: 'OTHER' as any,
        verdictRaw: record.verdict || null,
        language: record.language || null,
        rawDetail: record,
      },
      update: {
        verdictRaw: record.verdict || null,
        language: record.language || null,
        rawDetail: record,
      },
    });
  }

  @Post('login/:platform')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Open browser login page for a platform' })
  async loginPlatform(@Param('platform') platform: string): Promise<{ accepted: boolean; platform: string; error?: string }> {
    this.logger.log(`Opening login page for platform: ${platform}`);

    const loginScript = this.loginScripts[platform];
    if (!loginScript) {
      this.logger.warn(`No login script configured for platform: ${platform}`);
      return { accepted: false, platform, error: `Unsupported platform: ${platform}` };
    }

    // Fire-and-forget: spawn Python script that opens browser for manual login
    this.pythonService
      .execute(loginScript, { platform })
      .then((result) => this.logger.log(`Login script completed: ${JSON.stringify(result)}`))
      .catch((err) => this.logger.error(`Login script failed: ${err.message}`));

    return { accepted: true, platform };
  }

  @Get('cookies/:platform')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Check cookie status for a platform' })
  checkCookies(@Param('platform') platform: string): { platform: string; hasCookies: boolean } {
    const cookiePath = path.resolve(this.dataDir, `../cookies/${platform}.json`);
    let hasCookies = false;
    try {
      const raw = JSON.parse(fs.readFileSync(cookiePath, 'utf-8'));
      // Support both formats: CookieManager { platform, cookies: [...] } or raw array [...]
      const cookies = Array.isArray(raw?.cookies) ? raw.cookies : (Array.isArray(raw) ? raw : []);
      hasCookies = cookies.length > 0;
    } catch {}
    return { platform, hasCookies };
  }

  // ── Bulk Async Crawl ──────────────────────────────────────────────────────────

  @Post('bulk/start')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Start async bulk crawl (supports 100,000+ problems)' })
  async startBulkCrawl(@Body() dto: BulkCrawlDto): Promise<{ jobId: string; status: string }> {
    const platform = dto.platform;
    const tags = dto.tags || null; // null = fetch all types, not just P
    const count = dto.count ?? 100;
    const phases = dto.phases || ['list', 'detail', 'solutions'];
    const skipExisting = dto.skipExisting !== false;

    // Prevent duplicate running jobs for the same platform
    const existing = await this.prisma.crawlJob.findFirst({
      where: { platform: platform as any, status: 'running' },
    });
    if (existing) {
      // 卡住超过 30 分钟 → 自动标记失败，允许新任务
      const STALE_MS = 30 * 60 * 1000;
      const age = Date.now() - new Date(existing.updatedAt).getTime();
      if (age > STALE_MS) {
        this.logger.warn(
          `Auto-failing stale job ${existing.id} (${platform}, idle for ${Math.round(age / 60000)}min)`,
        );
        await this.prisma.crawlJob.update({
          where: { id: existing.id },
          data: { status: 'failed', finishedAt: new Date() },
        });
      } else {
        throw new ConflictException(
          `Platform ${platform} already has a running bulk crawl (jobId=${existing.id}). Cancel it first or wait for completion.`
        );
      }
    }

    // Query existing sourceIds for skip
    let skipIds: string[] = [];
    try {
      const existingProblems = await this.prisma.$queryRaw<Array<{sourceId: string}>>`
        SELECT "source_id" as "sourceId" FROM "problems" WHERE "source_platform" = ${platform}::"Platform"
      `;
      skipIds = existingProblems.map((p) => p.sourceId);
    } catch (err: any) {
      this.logger.warn(`Failed to query existing problems for skip: ${err?.message || err}`);
    }

    // Create CrawlJob record
    const job = await this.prisma.crawlJob.create({
      data: {
        platform: platform as any,
        status: 'running',
        phase: 'list',
        config: { tags, count, phases, skipExisting },
        stateFile: path.resolve(this.dataDir, platform, '_crawl_state.json'),
        startedAt: new Date(),
      },
    });

    this.logger.log(`Bulk crawl started: jobId=${job.id}, platform=${platform}, tags=${tags}, count=${count}, phases=${phases.join(',')}`);

    // Fire-and-forget: spawn Python process in background
    const params = {
      platform,
      tags,
      count,
      job_id: job.id,
      phases,
      skip_ids: skipIds,
      skip_existing: skipExisting,
    };

    const child = this.pythonService.spawn('crawlers/bulk_crawl.py', params, job.id);

    child.on('exit', async (code) => {
      try {
        if (code === 0) {
          await this.prisma.crawlJob.update({
            where: { id: job.id },
            data: { status: 'completed', phase: null, finishedAt: new Date() },
          });
          this.logger.log(`Bulk crawl completed: jobId=${job.id}`);
          // Auto-import after completion
          try {
            const imported = await this.importPlatformData(platform);
            await this.prisma.crawlJob.update({
              where: { id: job.id },
              data: { summary: { imported: imported.total } },
            });
            this.logger.log(`Auto-import done for bulk crawl ${job.id}: ${imported.total} records (${imported.problems} problems, ${imported.solutions} solutions, ${imported.records} records)`);
            // Fire-and-forget: auto-summarize newly imported problems
            if (imported.total > 0) {
              this.summarizeUnprocessed(platform, job.id, imported.problemSourceIds)
                .then((r) => this.logger.log(`Auto-summarize done for bulk crawl ${job.id}: ${r.embedded} summarized, ${r.skipped} skipped`))
                .catch((err) => this.logger.error(`Auto-summarize failed for bulk crawl ${job.id}: ${err?.message || err}`));
            }
          } catch (importErr: any) {
            this.logger.error(`Auto-import failed for bulk crawl ${job.id}: ${importErr?.message || importErr}`);
          }
        } else {
          await this.prisma.crawlJob.update({
            where: { id: job.id },
            data: { status: 'failed', finishedAt: new Date() },
          });
          this.logger.error(`Bulk crawl failed: jobId=${job.id}, exitCode=${code}`);
        }
      } catch (dbErr: any) {
        this.logger.error(`Failed to update CrawlJob on exit: ${dbErr?.message || dbErr}`);
      }
    });

    child.on('error', async (err) => {
      try {
        await this.prisma.crawlJob.update({
          where: { id: job.id },
          data: { status: 'failed', finishedAt: new Date(), errors: { spawn_error: err.message } },
        });
      } catch (_) {}
    });

    return { jobId: job.id, status: 'started' };
  }

  @Get('bulk/:jobId/progress')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: 'Get progress of a bulk crawl job' })
  async getBulkProgress(@Param('jobId') jobId: string): Promise<any> {
    const job = await this.prisma.crawlJob.findUnique({ where: { id: jobId } });
    if (!job) {
      throw new NotFoundException(`CrawlJob ${jobId} not found`);
    }

    // Read live state file if it exists
    let fileState: any = {};
    const stateFile = job.stateFile || path.resolve(this.dataDir, job.platform, '_crawl_state.json');
    try {
      if (fs.existsSync(stateFile)) {
        fileState = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
      }
    } catch (err: any) {
      this.logger.warn(`Failed to read state file for ${jobId}: ${err?.message || err}`);
    }

    // Merge DB status with file progress
    const dbStatus = job.status;
    const phase = fileState.phase || job.phase || null;

    // Build progress breakdown per phase
    const phases = fileState.phases || {};
    const currentPhase = phases[phase as string] || null;

    // Calculate ETA
    let eta: string | null = null;
    if (currentPhase && currentPhase.status === 'running' && currentPhase.total && currentPhase.fetched) {
      const remaining = currentPhase.total - currentPhase.fetched;
      const avgMs = (currentPhase.avg_ms_per_item || 500); // default 500ms per item
      const remainingMs = remaining * avgMs;
      if (remainingMs > 0) {
        eta = new Date(Date.now() + remainingMs).toISOString();
      }
    }

    // Elapsed time
    let elapsedSeconds: number | null = null;
    if (job.startedAt) {
      elapsedSeconds = Math.floor((Date.now() - new Date(job.startedAt).getTime()) / 1000);
    }

    return {
      jobId: job.id,
      platform: job.platform,
      status: dbStatus,
      phase,
      phases,
      errors: fileState.errors || [],
      summary: fileState.summary || job.summary || null,
      elapsed: elapsedSeconds,
      eta,
      startedAt: job.startedAt?.toISOString() || null,
      finishedAt: job.finishedAt?.toISOString() || null,
    };
  }

  @Post('bulk/:jobId/cancel')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(200)
  @ApiOperation({ summary: 'Cancel a running bulk crawl job' })
  async cancelBulkCrawl(@Param('jobId') jobId: string): Promise<{ cancelled: boolean }> {
    const job = await this.prisma.crawlJob.findUnique({ where: { id: jobId } });
    if (!job) {
      throw new NotFoundException(`CrawlJob ${jobId} not found`);
    }
    if (job.status !== 'running') {
      return { cancelled: false };
    }

    const killed = this.pythonService.cancelJob(jobId);
    await this.prisma.crawlJob.update({
      where: { id: jobId },
      data: { status: 'cancelled', finishedAt: new Date() },
    });

    this.logger.log(`Bulk crawl cancelled: jobId=${jobId}, processKilled=${killed}`);
    return { cancelled: true };
  }

  @Get('bulk/jobs')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: 'List recent bulk crawl jobs' })
  async listBulkJobs(@Query('status') status?: string, @Query('limit') limit?: string): Promise<{ jobs: any[] }> {
    const where: any = {};
    if (status) {
      where.status = status;
    }
    const jobs = await this.prisma.crawlJob.findMany({
      where,
      orderBy: { createdAt: 'desc' },
      take: Math.min(Number(limit) || 20, 100),
      select: {
        id: true,
        platform: true,
        status: true,
        phase: true,
        config: true,
        summary: true,
        startedAt: true,
        finishedAt: true,
        createdAt: true,
      },
    });
    return { jobs };
  }

  @Get('embed-progress/:jobId')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: 'Get embed progress for a crawl job' })
  async getEmbedProgress(@Param('jobId') jobId: string): Promise<{
    jobId: string; platform: string; embedTotal: number; embedDone: number; skipped: number;
    done: boolean; summary?: any; logLines?: Array<{ time: string; message: string; level: string }>;
  }> {
    const job = await this.prisma.crawlJob.findUnique({ where: { id: jobId } });
    if (!job) throw new NotFoundException(`CrawlJob ${jobId} not found`);

    const embedTotal = job.embedTotal ?? 0;
    const embedDone = job.embedDone ?? 0;
    const summary = (job.summary || {}) as any;
    const skipped = summary?.skipped ?? 0;
    return {
      jobId: job.id,
      platform: job.platform,
      embedTotal,
      embedDone,
      skipped,
      done: embedTotal > 0 && embedDone >= embedTotal,
      summary,
      logLines: summary.logLines || [],
    };
  }

  @Post('backfill-solutions/:platform')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(200)
  @ApiOperation({ summary: 'Backfill solutions for all problems' })
  async backfillSolutions(@Param('platform') platform: string): Promise<{ fetched: number; errors: number }> {
    const problems = await this.prisma.problem.findMany({
      where: { sourcePlatform: platform as any },
      select: { sourceId: true, title: true },
    });

    const script = this.platformScripts[platform] || 'crawlers/luogu.py';

    this.logger.log(`Backfilling solutions for ${problems.length} problems on ${platform}`);
    let fetched = 0, errors = 0;

    for (const p of problems) {
      try {
        const result: any = await this.pythonService.execute(script, {
          action: 'fetch_solutions',
          uid: p.sourceId,
        });
        if (result?.success && Array.isArray(result?.data)) {
          const count = result.data.length;
          if (count > 0) {
            await this.upsertSolutions(platform, result.data, p.sourceId);
            fetched += count;
            this.logger.log(`Solutions for ${p.sourceId}: ${count} imported`);
          }
        }
      } catch (err: any) {
        errors++;
        this.logger.warn(`Solution backfill error for ${p.sourceId}: ${err?.message || err}`);
      }
    }

    this.logger.log(`Solution backfill done: ${fetched} solutions, ${errors} errors`);
    return { fetched, errors };
  }

  @Post('backfill-content/:platform')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(200)
  @ApiOperation({ summary: 'Backfill fullContent for problems (force=true to reprocess all)' })
  async backfillContent(
    @Param('platform') platform: string,
    @Query('force') force?: string,
  ): Promise<{ backfilled: number; errors: number }> {
    const where: any = { sourcePlatform: platform as any };
    if (force !== 'true') {
      where.OR = [{ fullContent: null }, { fullContent: '' }];
    }

    const problems = await this.prisma.problem.findMany({
      where,
      select: { id: true, sourceId: true, title: true, rawDetail: true },
    });

    this.logger.log(`Backfilling content for ${problems.length} problems on ${platform} (force=${force || 'false'})`);
    let backfilled = 0, errors = 0;

    for (const p of problems) {
      try {
        const script = this.platformScripts[platform] || 'crawlers/luogu.py';
        // Try re-crawling from API first to get fresh data (e.g. with new Accept-Language)
        const result: any = await this.pythonService.execute(script, {
          action: 'fetch_detail',
          uid: p.sourceId,
        });
        if (result?.success && result?.data) {
          const fullContent = this.buildFullContent(platform, result.data);
          if (fullContent) {
            await this.prisma.problem.update({
              where: { id: p.id },
              data: { fullContent },
            });
            backfilled++;
            this.logger.log(`Backfilled ${p.sourceId}: ${p.title}`);
            continue;
          }
        }

        // Fallback: rebuild from stored rawDetail if API fetch fails
        if (p.rawDetail) {
          const fullContent = this.buildFullContent(platform, p.rawDetail as any);
          if (fullContent) {
            await this.prisma.problem.update({
              where: { id: p.id },
              data: { fullContent },
            });
            backfilled++;
            this.logger.log(`Backfilled from rawDetail ${p.sourceId}: ${p.title}`);
            continue;
          }
        }

        errors++;
        this.logger.warn(`Failed to backfill ${p.sourceId}: no content sources available`);
      } catch (err: any) {
        errors++;
        this.logger.warn(`Backfill error for ${p.sourceId}: ${err?.message || err}`);
      }
    }

    this.logger.log(`Backfill done: ${backfilled} ok, ${errors} errors`);
    return { backfilled, errors };
  }

  /**
   * Thin wrapper over the shared pure helper in {@link fullcontent.util}.
   * Extraction was required so the data-migration scripts can reuse the
   * exact same logic (the previous 4 divergent copies are how the AtCoder
   * data-loss bug recurred).
   */
  /** Build fullContent from a crawl record using the standard section format. */
  private buildFullContent(platform: string, record: any): string {
    return buildFullContentUtil(platform, record);
  }


  @Post('normalize-difficulty')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(200)
  @ApiOperation({ summary: 'Re-normalize all problems difficulty based on platform mapping' })
  async normalizeAllDifficulties(): Promise<{ updated: number }> {
    const problems = await this.prisma.problem.findMany({
      select: { id: true, sourcePlatform: true, difficultyRaw: true },
    });
    let updated = 0;
    for (const p of problems) {
      const normalized = this.normalizeDifficulty(p.sourcePlatform, p.difficultyRaw);
      if (p.difficultyRaw && normalized !== 0) {
        await this.prisma.problem.update({
          where: { id: p.id },
          data: { difficultyNormalized: normalized },
        });
        updated++;
      }
    }
    this.logger.log(`Normalized ${updated} of ${problems.length} problems`);
    return { updated };
  }

  @Post('summarize/:platform')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Trigger LLM summarization for unprocessed problems' })
  async triggerSummarize(
    @Param('platform') platform: string,
    @Query('force') force?: string,
  ): Promise<{ accepted: boolean; platform: string; embedJobId: string }> {
    this.logger.log(`Triggering summarization for platform: ${platform} (force=${force || 'false'})`);
    if (force === 'true') {
      // Clear existing summaries to force regeneration
      await this.prisma.problem.updateMany({
        where: { sourcePlatform: platform as any },
        data: { solutionSummary: null },
      });
    }
    // Create CrawlJob for embed progress tracking
    const embedJob = await this.prisma.crawlJob.create({
      data: {
        platform: platform as any,
        status: 'running',
        phase: 'import_',
        config: { type: 'embed', sourceAction: 'manual' },
        startedAt: new Date(),
      },
    });
    this.summarizeUnprocessed(platform, embedJob.id)
      .then(async (r) => {
        this.logger.log(`Summarization done for ${platform}: ${r.embedded} processed, ${r.skipped} skipped`);
        await this.prisma.crawlJob.update({
          where: { id: embedJob.id },
          data: { status: 'completed', finishedAt: new Date(), summary: { embedded: r.embedded, skipped: r.skipped } },
        }).catch(() => {});
      })
      .catch(async (err) => {
        this.logger.error(`Summarization failed for ${platform}: ${err?.message || err}`);
        await this.prisma.crawlJob.update({
          where: { id: embedJob.id },
          data: { status: 'failed', finishedAt: new Date() },
        }).catch(() => {});
      });
    return { accepted: true, platform, embedJobId: embedJob.id };
  }

  @Post('batch-embed/all')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Clear all vectors and re-summarize + re-embed ALL problems across all platforms (concurrency=40)' })
  async batchEmbedAll(): Promise<{ accepted: boolean; embedJobId: string }> {
    this.logger.log('Starting batch-embed/all: clear all vectors, re-summarize + re-embed all problems');

    const embedJob = await this.prisma.crawlJob.create({
      data: {
        platform: 'luogu' as any, // dummy platform — batch spans all
        status: 'running',
        phase: 'import_',
        config: { type: 'batch-embed', scope: 'all' },
        startedAt: new Date(),
      },
    });

    // Fire-and-forget
    this.runBatchEmbedAll(embedJob.id)
      .then(async (stats) => {
        this.logger.log(`Batch-embed/all done: ${JSON.stringify(stats)}`);
        await this.prisma.crawlJob.update({
          where: { id: embedJob.id },
          data: { status: 'completed', finishedAt: new Date(), summary: stats },
        }).catch(() => {});
      })
      .catch(async (err) => {
        this.logger.error(`Batch-embed/all failed: ${err?.message || err}`);
        await this.prisma.crawlJob.update({
          where: { id: embedJob.id },
          data: { status: 'failed', finishedAt: new Date() },
        }).catch(() => {});
      });

    return { accepted: true, embedJobId: embedJob.id };
  }

  @Post('batch-embed/missing')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Only summarize + embed problems missing summary, incomplete summary, or missing vector (no full reset)' })
  async batchEmbedMissing(): Promise<{ accepted: boolean; embedJobId: string }> {
    this.logger.log('Starting batch-embed/missing: only missing/incomplete summaries + missing vectors');

    const embedJob = await this.prisma.crawlJob.create({
      data: {
        platform: 'luogu' as any,
        status: 'running',
        phase: 'import_',
        config: { type: 'batch-embed', scope: 'missing' },
        startedAt: new Date(),
      },
    });

    this.runBatchEmbedMissing(embedJob.id)
      .then(async (stats) => {
        this.logger.log(`Batch-embed/missing done: ${JSON.stringify(stats)}`);
        await this.prisma.crawlJob.update({
          where: { id: embedJob.id },
          data: { status: 'completed', finishedAt: new Date(), summary: stats },
        }).catch(() => {});
      })
      .catch(async (err) => {
        this.logger.error(`Batch-embed/missing failed: ${err?.message || err}`);
        await this.prisma.crawlJob.update({
          where: { id: embedJob.id },
          data: { status: 'failed', finishedAt: new Date() },
        }).catch(() => {});
      });

    return { accepted: true, embedJobId: embedJob.id };
  }

  @Get('logs')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: 'Recent crawl logs (placeholder)' })
  getRecentLogs(): { message: string } {
    return { message: 'Crawl logs endpoint is a placeholder. Query push_logs for history.' };
  }

  // ── Basic Summary Generator (fallback when no LLM API key) ──────────


  // ── LLM Summarization ───────────────────────────────────────────────

  /**
   * Summarize ALL unprocessed problems for a platform, generating AI summaries
   * and vector embeddings.  Optionally updates a CrawlJob for progress tracking.
   *
   * @param jobId  If provided, CrawlJob.embedTotal/embedDone are updated in real time.
   */
  async summarizeUnprocessed(platform: string, jobId?: string, sourceIds?: string[]): Promise<{ embedded: number; skipped: number }> {
    // Skip if no LLM API key configured — summarization requires DeepSeek
    const deepSeekConfig = this.resolveDeepSeekConfig();
    if (!deepSeekConfig) {
      this.logger.log('No DeepSeek API key configured, skipping summarization and embedding');
      if (jobId) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedTotal: 0, embedDone: 0, status: 'completed', finishedAt: new Date() },
        }).catch(() => {});
      }
      return { embedded: 0, skipped: 0 };
    }

    // Build WHERE clause — if sourceIds provided, only target those specific problems
    const whereBase: any = { sourcePlatform: platform as any };
    if (sourceIds && sourceIds.length > 0) {
      whereBase.sourceId = { in: sourceIds };
    }

    // Count total unprocessed (for progress tracking)
    const totalUnprocessed = await this.prisma.problem.count({
      where: {
        ...whereBase,
        OR: [{ solutionSummary: null }, { solutionSummary: '' }],
      },
    });

    const skipped = (sourceIds && sourceIds.length > 0) ? sourceIds.length - totalUnprocessed : 0;

    if (totalUnprocessed === 0) {
      this.logger.log(`No unprocessed problems for ${platform} (skipped ${skipped} already complete)`);
      if (jobId) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedTotal: 0, embedDone: 0, summary: { embedded: 0, skipped } },
        }).catch(() => {});
      }
      return { embedded: 0, skipped };
    }

    // Set embedTotal on CrawlJob
    if (jobId) {
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { embedTotal: totalUnprocessed, embedDone: 0, summary: { skipped } },
      }).catch(() => {});
    }

    let count = 0;
    const batchSize = 50; // Fetch in batches to avoid memory issues
    let offset = 0;

    while (true) {
      const unprocessed = await this.prisma.problem.findMany({
        where: {
          ...whereBase,
          OR: [{ solutionSummary: null }, { solutionSummary: '' }],
        },
        select: { id: true, title: true, sourceId: true, fullContent: true, difficultyRaw: true },
        take: batchSize,
        skip: offset,
      });

      if (unprocessed.length === 0) break;

      for (const p of unprocessed) {
        try {
          const summary = await this.callDeepSeekSummarize(p.title, p.fullContent || '', p.difficultyRaw || '');
          if (summary) {
            await this.prisma.problem.update({
              where: { id: p.id },
              data: { solutionSummary: summary },
            });

            // Generate and store vector embedding from solution_summary only
            try {
              const vec = await this.vectorService.embedText(summary);
              await this.vectorService.setProblemVector(p.id, vec);
            } catch (embedErr: any) {
              this.logger.warn(`Embedding failed for ${p.sourceId}: ${embedErr?.message || embedErr}`);
            }

            count++;
            this.logger.log(`Summarized ${p.sourceId}: ${p.title} (${count}/${totalUnprocessed})`);

            // Update CrawlJob progress
            if (jobId) {
              try {
                await this.prisma.crawlJob.update({
                  where: { id: jobId },
                  data: { embedDone: count },
                });
              } catch (_) {}
            }
          }
        } catch (err: any) {
          this.logger.warn(`Summarize failed for ${p.sourceId}: ${err?.message || err}`);
        }

        // Rate-limit guard: pause between API calls to avoid RPM/QPS throttling.
        // DEEPSEEK_RPM controls max requests per minute; DEEPSEEK_CALL_DELAY_MS
        // directly sets the inter-call delay (overrides RPM calculation).
        const callDelayMs = this._getSummarizeCallDelay();
        if (callDelayMs > 0) {
          await new Promise((r) => setTimeout(r, callDelayMs));
        }
      }

      // If we got fewer than batchSize, we've processed everything
      if (unprocessed.length < batchSize) break;
      // Don't increment offset — we're deleting processed items, so offset stays 0
    }

    return { embedded: count, skipped };
  }

  /**
   * Compute inter-call delay for summarization to stay within rate limits.
   *
   * Priority:
   *  1. DEEPSEEK_CALL_DELAY_MS  — explicit delay in ms
   *  2. DEEPSEEK_RPM            — max requests per minute → delay = 60000 / RPM
   *  3. Default: 3000ms for aliyun, 0ms for deepseek official
   */
  private _getSummarizeCallDelay(): number {
    const explicit = parseInt(process.env.DEEPSEEK_CALL_DELAY_MS || '', 10);
    if (!isNaN(explicit) && explicit >= 0) return explicit;

    const rpm = parseInt(process.env.DEEPSEEK_RPM || '', 10);
    if (!isNaN(rpm) && rpm > 0) return Math.ceil(60000 / rpm);

    // Default conservative delay for aliyun free tier
    const provider = (process.env.DEEPSEEK_PROVIDER || 'deepseek').trim().toLowerCase();
    if (provider === 'aliyun') return 3000;

    return 0;
  }

  // ── DeepSeek Config Resolver ───────────────────────────────────────────

  /**
   * Resolve DeepSeek API config.
   *
   * DEEPSEEK_PROVIDER=aliyun  → 阿里云百炼 DeepSeek
   * DEEPSEEK_PROVIDER=deepseek (or unset) → 官方 DeepSeek
   * DEEPSEEK_BASE_URL 可覆盖默认 base URL
   */
  private resolveDeepSeekConfig(): { apiKey: string; baseUrl: string; model: string } | null {
    const apiKey = (process.env.DEEPSEEK_API_KEY || '').trim();
    if (!apiKey || apiKey === 'sk-placeholder') return null;

    const provider = (process.env.DEEPSEEK_PROVIDER || 'deepseek').trim().toLowerCase();
    const model = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';

    let baseUrl = process.env.DEEPSEEK_BASE_URL || '';
    if (!baseUrl) {
      baseUrl = provider === 'aliyun'
        ? 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        : 'https://api.deepseek.com/v1';
    }
    // 向后兼容：旧配置无 /v1 后缀的自动追加
    if (!baseUrl.endsWith('/v1') && !baseUrl.endsWith('/v2') && !baseUrl.includes('/compatible-mode/')) {
      baseUrl = baseUrl.replace(/\/$/, '') + '/v1';
    }

    return { apiKey, baseUrl, model };
  }

  private async callDeepSeekSummarize(title: string, content: string, difficultyRaw: string): Promise<string | null> {
    const config = this.resolveDeepSeekConfig();
    if (!config) {
      this.logger.debug('DeepSeek API key not configured, skipping summarization');
      return null;
    }

    const truncated = content.length > 3000 ? content.slice(0, 3000) : content;
    const prompt = `You are an expert competitive programming analyst. Summarize the following problem concisely.

Title: ${title}
Difficulty: ${difficultyRaw}
Content: ${truncated}

Return a Chinese summary with these sections (2-3 sentences each):
【核心考点】...
【推荐解法】...
【易错点】...`;

    const timeoutMs = parseInt(process.env.DEEPSEEK_TIMEOUT_MS || '300000', 10);
    const maxRetries = parseInt(process.env.DEEPSEEK_MAX_RETRIES || '3', 10);

    let lastErr: Error | null = null;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);

        const resp = await fetch(`${config.baseUrl}/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${config.apiKey}` },
          body: JSON.stringify({
            model: config.model,
            messages: [{ role: 'user', content: prompt }],
            temperature: 0.3,
            max_tokens: 4096,
            thinking: { type: 'disabled' },
          }),
          signal: controller.signal,
        });
        clearTimeout(timer);

        if (!resp.ok) {
          const errText = await resp.text().catch(() => '');
          // Rate limit (429) → retry with backoff, respecting Retry-After header
          if (resp.status === 429 && attempt < maxRetries) {
            const retryAfterSec = parseInt(resp.headers.get('Retry-After') || '', 10);
            const delay = retryAfterSec > 0 ? retryAfterSec * 1000 : 2 ** (attempt + 1) * 2000;
            this.logger.warn(
              `DeepSeek rate limited (429) for ${title}, retrying in ${delay}ms (attempt ${attempt + 1}/${maxRetries})`,
            );
            await new Promise((r) => setTimeout(r, delay));
            lastErr = new Error(`DeepSeek API error 429: ${errText.slice(0, 200)}`);
            continue;
          }
          // Server error (5xx) → retryable
          if (resp.status >= 500 && attempt < maxRetries) {
            const delay = 2 ** (attempt + 1) * 2000;
            this.logger.warn(
              `DeepSeek server error ${resp.status} for ${title}, retrying in ${delay}ms (attempt ${attempt + 1}/${maxRetries})`,
            );
            await new Promise((r) => setTimeout(r, delay));
            lastErr = new Error(`DeepSeek API error ${resp.status}: ${errText.slice(0, 200)}`);
            continue;
          }
          throw new Error(`DeepSeek API error ${resp.status}: ${errText.slice(0, 200)}`);
        }

        const data: any = await resp.json();
        return data?.choices?.[0]?.message?.content || null;
      } catch (err: any) {
        lastErr = err instanceof Error ? err : new Error(String(err));
        const isRetryable =
          err.name === 'AbortError' ||
          err.message?.includes('fetch failed') ||
          err.message?.includes('ETIMEDOUT') ||
          err.message?.includes('ECONNRESET') ||
          err.message?.includes('ECONNREFUSED') ||
          err.message?.includes('ENOTFOUND');
        if (isRetryable && attempt < maxRetries) {
          const delay = 2 ** (attempt + 1) * 2000; // 4s, 8s, 16s
          this.logger.warn(
            `DeepSeek summarize attempt ${attempt + 1} failed for ${title} (${lastErr.message}), retrying in ${delay}ms`,
          );
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }
        // Non-retryable → throw immediately; retryable-but-exhausted → fall through
        if (!isRetryable) throw err;
      }
    }

    throw new Error(`DeepSeek summarize failed after ${maxRetries + 1} attempts: ${lastErr?.message}`);
  }

  /**
   * 全量批量处理：清空所有向量 → 补全摘要 → 嵌入向量
   * 并发数 = 200（基于 worker 竞争队列）
   */
  private async runBatchEmbedAll(jobId: string): Promise<{
    total: number; cleared: number; summarized: number; embedded: number; skipped: number; errors: number;
  }> {
    const POOL = 200;
    const stats = { total: 0, cleared: 0, summarized: 0, embedded: 0, skipped: 0, errors: 0 };
    const logLines: Array<{ time: string; message: string; level: string }> = [];

    const flushLogs = async () => {
      if (!jobId || logLines.length === 0) return;
      // 只保留最近 200 条日志行，避免 JSON 膨胀
      const recent = logLines.slice(-200);
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { summary: { logLines: recent, stats } },
      }).catch(() => {});
    };

    const addLine = (message: string, level: string = 'info') => {
      const time = new Date().toISOString();
      logLines.push({ time, message, level });
      this.logger.log(`[batch-embed] ${message}`);
    };

    // ── Step 0: 清空所有向量 ─────────────────────────────────────
    const clearResult: any = await this.prisma.$executeRaw`
      UPDATE problems
      SET vector_embedding = NULL, updated_at = NOW()
      WHERE vector_embedding IS NOT NULL
    `;
    stats.cleared = clearResult;
    addLine(`清空 ${stats.cleared} 条旧向量`);

    // ── Step 1: 拉取全量题目 ─────────────────────────────────────
    const rows: any[] = await this.prisma.$queryRaw`
      SELECT id, source_id::text, title, full_content, solution_summary, difficulty_raw
      FROM problems
      WHERE deleted_at IS NULL
      ORDER BY created_at DESC
    `;
    stats.total = rows.length;
    const needSummary = rows.filter((r: any) => !r.solution_summary || String(r.solution_summary).trim().length === 0).length;
    addLine(`共 ${stats.total} 题，需生成摘要: ${needSummary}，仅需嵌入: ${stats.total - needSummary}`);

    if (stats.total === 0) {
      if (jobId) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedTotal: 0, embedDone: 0 },
        }).catch(() => {});
      }
      return stats;
    }

    if (jobId) {
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { embedTotal: stats.total, embedDone: 0 },
      }).catch(() => {});
    }

    // ── Step 2: worker 竞争队列并发处理 ───────────────────────────
    const queue = rows.slice();
    let completed = 0;

    const processOne = async (p: any): Promise<void> => {
      let summary = p.solution_summary;

      // 检查三个必要段落是否都存在、末尾是否完整结束
      const hasAllSections = (s: string | null | undefined): boolean => {
        if (!s || s.trim().length === 0) return false;
        return /【核心考点】/.test(s) && /【推荐解法】/.test(s) && /【易错点】/.test(s)
          && /[。.！!？?）)]\s*$/.test(s.trim());
      };

      // 无摘要或摘要不完整 → 重新生成摘要
      if (!hasAllSections(summary)) {
        try {
          summary = await this.callDeepSeekSummarize(
            p.title,
            p.full_content || '',
            p.difficulty_raw || '',
          );
          if (summary) {
            await this.prisma.$executeRaw`
              UPDATE problems
              SET solution_summary = ${summary}, updated_at = NOW()
              WHERE id = ${p.id}::uuid
            `;
            stats.summarized++;
          }
        } catch (err: any) {
          stats.errors++;
          addLine(`[ERR] summarize ${p.source_id}: ${err?.message || err}`, 'error');
          return;
        }
      }

      // 有摘要 → 生成向量
      if (summary && String(summary).trim().length > 0) {
        try {
          const vec = await this.vectorService.embedText(String(summary));
          await this.vectorService.setProblemVector(p.id, vec);
          stats.embedded++;
        } catch (err: any) {
          stats.errors++;
          addLine(`[ERR] embed ${p.source_id}: ${err?.message || err}`, 'error');
          return;
        }
      } else {
        stats.skipped++;
      }

      completed++;
      if (completed % 500 === 0) {
        addLine(
          `${completed}/${stats.total} (${((completed / stats.total) * 100).toFixed(1)}%) — summarized=${stats.summarized} embedded=${stats.embedded} skipped=${stats.skipped} errors=${stats.errors}`,
          'success',
        );
        await flushLogs();
      }
      if (jobId && completed % 10 === 0) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedDone: completed },
        }).catch(() => {});
      }
    };

    const worker = async () => {
      while (queue.length > 0) {
        const item = queue.shift();
        if (!item) break;
        await processOne(item);
      }
    };

    const workers = Array.from({ length: Math.min(POOL, stats.total) }, () => worker());
    await Promise.all(workers);

    // 最终更新进度 + 日志
    addLine(
      `完成！summarized=${stats.summarized} embedded=${stats.embedded} skipped=${stats.skipped} errors=${stats.errors}`,
      'success',
    );
    if (jobId) {
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { embedDone: completed },
      }).catch(() => {});
    }
    await flushLogs();

    return stats;
  }

  /**
   * 增量补全：仅处理 summary 缺失/不完整 或 vector_embedding 缺失的题目
   * 不清空任何已有向量，不做全量重建
   */
  private async runBatchEmbedMissing(jobId: string): Promise<{
    total: number; summarized: number; embedded: number; skipped: number; errors: number;
  }> {
    const POOL = 200;
    const stats = { total: 0, summarized: 0, embedded: 0, skipped: 0, errors: 0 };
    const logLines: Array<{ time: string; message: string; level: string }> = [];

    const flushLogs = async () => {
      if (!jobId || logLines.length === 0) return;
      const recent = logLines.slice(-200);
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { summary: { logLines: recent, stats } },
      }).catch(() => {});
    };

    const addLine = (message: string, level: string = 'info') => {
      const time = new Date().toISOString();
      logLines.push({ time, message, level });
      this.logger.log(`[batch-embed-missing] ${message}`);
    };

    // ── Step 0: 检测哪些题目需要补充 ─────────────────────────────
    // 缺失摘要 / 摘要不完整 / 缺少向量
    const rows: any[] = await this.prisma.$queryRaw`
      SELECT id, source_id::text, title, full_content, solution_summary, difficulty_raw,
             vector_embedding IS NOT NULL AS has_vector
      FROM problems
      WHERE deleted_at IS NULL
        AND (
          -- 无摘要
          solution_summary IS NULL OR solution_summary = ''
          OR
          -- 摘要不完整（缺少三个必要段落之一 或 结尾不完整）
          NOT (
            solution_summary ~ '【核心考点】'
            AND solution_summary ~ '【推荐解法】'
            AND solution_summary ~ '【易错点】'
            AND solution_summary ~ '[。.!！?？)）]\\s*$'
          )
          OR
          -- 有完整摘要但无向量
          vector_embedding IS NULL
        )
      ORDER BY created_at DESC
    `;
    stats.total = rows.length;
    addLine(`共需补全 ${stats.total} 题（缺失/不完整摘要 或 无向量）`);

    if (stats.total === 0) {
      addLine('所有题目均完整，无需补全', 'success');
      if (jobId) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedTotal: 0, embedDone: 0 },
        }).catch(() => {});
      }
      await flushLogs();
      return stats;
    }

    if (jobId) {
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { embedTotal: stats.total, embedDone: 0 },
      }).catch(() => {});
    }

    // ── Step 1: worker 竞争队列并发处理 ───────────────────────────
    const queue = rows.slice();
    let completed = 0;

    const processOne = async (p: any): Promise<void> => {
      let summary = p.solution_summary;

      // 检查三个必要段落是否都存在、末尾是否完整结束
      const hasAllSections = (s: string | null | undefined): boolean => {
        if (!s || s.trim().length === 0) return false;
        return /【核心考点】/.test(s) && /【推荐解法】/.test(s) && /【易错点】/.test(s)
          && /[。.！!？?）)]\s*$/.test(s.trim());
      };

      // 无摘要或摘要不完整 → 重新生成摘要
      if (!hasAllSections(summary)) {
        try {
          summary = await this.callDeepSeekSummarize(
            p.title,
            p.full_content || '',
            p.difficulty_raw || '',
          );
          if (summary) {
            await this.prisma.$executeRaw`
              UPDATE problems
              SET solution_summary = ${summary}, updated_at = NOW()
              WHERE id = ${p.id}::uuid
            `;
            stats.summarized++;
          }
        } catch (err: any) {
          stats.errors++;
          addLine(`[ERR] summarize ${p.source_id}: ${err?.message || err}`, 'error');
          return;
        }
      }

      // 有摘要但无向量 → 只生成向量
      if (summary && String(summary).trim().length > 0) {
        try {
          const vec = await this.vectorService.embedText(String(summary));
          await this.vectorService.setProblemVector(p.id, vec);
          stats.embedded++;
        } catch (err: any) {
          stats.errors++;
          addLine(`[ERR] embed ${p.source_id}: ${err?.message || err}`, 'error');
          return;
        }
      } else {
        stats.skipped++;
      }

      completed++;
      if (completed % 500 === 0) {
        addLine(
          `${completed}/${stats.total} (${((completed / stats.total) * 100).toFixed(1)}%) — summarized=${stats.summarized} embedded=${stats.embedded} skipped=${stats.skipped} errors=${stats.errors}`,
          'success',
        );
        await flushLogs();
      }
      if (jobId && completed % 10 === 0) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedDone: completed },
        }).catch(() => {});
      }
    };

    const worker = async () => {
      while (queue.length > 0) {
        const item = queue.shift();
        if (!item) break;
        await processOne(item);
      }
    };

    const workers = Array.from({ length: Math.min(POOL, stats.total) }, () => worker());
    await Promise.all(workers);

    addLine(
      `完成！summarized=${stats.summarized} embedded=${stats.embedded} skipped=${stats.skipped} errors=${stats.errors}`,
      'success',
    );
    if (jobId) {
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { embedDone: completed },
      }).catch(() => {});
    }
    await flushLogs();

    return stats;
  }
}
