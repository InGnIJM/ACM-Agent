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
      let importDetail = { problems: 0, solutions: 0, records: 0, total: 0 };
      let embedJobId: string | null = null;
      if (result?.success && dto.platform) {
        try {
          importDetail = await this.importPlatformData(dto.platform);
          this.logger.log(`Import completed for ${dto.platform}: ${importDetail.total} records upserted (${importDetail.problems} problems, ${importDetail.solutions} solutions, ${importDetail.records} records)`);

          // Only auto-summarize if DeepSeek API key is configured
          const hasApiKey = !!(process.env.DEEPSEEK_API_KEY && process.env.DEEPSEEK_API_KEY !== 'sk-placeholder');
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
            this.summarizeUnprocessed(dto.platform, embedJob.id)
              .then(async (n) => {
                this.logger.log(`Auto-summarize done for ${dto.platform}: ${n} problems summarized`);
                await this.prisma.crawlJob.update({
                  where: { id: embedJob.id },
                  data: { status: 'completed', finishedAt: new Date(), summary: { embedded: n } },
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
  private async importPlatformData(platform: string): Promise<{ problems: number; solutions: number; records: number; total: number }> {
    const platformDir = path.join(this.dataDir, platform);
    this.logger.log(`[IMPORT] platform=${platform} dataDir=${this.dataDir} platformDir=${platformDir}`);
    if (!fs.existsSync(platformDir)) {
      this.logger.warn(`[IMPORT] No data directory for platform ${platform}: ${platformDir}`);
      return { problems: 0, solutions: 0, records: 0, total: 0 };
    }

    let problems = 0;
    let solutions = 0;
    let recordsCount = 0;
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
              const sid = platform === 'leetcode'
                ? (record.titleSlug || record.slug || record.questionId || record.questionFrontendId)
                : (record.source_id || record.pid || record.id);
              this.logger.log(`[IMPORT]       upsertProblem: sourceId=${sid} title=${(record.title || record.name || '?').slice(0, 30)}`);
              await this.upsertProblem(platform, record);
              problems++;
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
    return { problems, solutions, records: recordsCount, total };
  }

  private async upsertProblem(platform: string, record: any): Promise<void> {
    // Codeforces: construct sourceId from contestId+index (e.g. "2236C")
    const cfId = record.contestId && record.index ? `${record.contestId}${record.index}` : null;
    // LeetCode: prefer titleSlug (natural identifier, matches solution filenames)
    let sourceId = platform === 'leetcode'
      ? (record.titleSlug || record.slug || record.questionId || record.questionFrontendId || record.source_id || record.pid || record.id)
      : (record.source_id || record.pid || record.id || cfId || record.titleSlug || record.questionId || record.questionFrontendId);
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
      const solutionIndex = sol.solution_index ?? (sol.vote_count ? sol.vote_count + Date.now() % 1000 : Date.now() % 10000);
      const upserted = await this.prisma.problemSolution.upsert({
        where: {
          problemId_solutionIndex: { problemId: problem.id, solutionIndex: Number(solutionIndex) % 100000 },
        },
        create: {
          problemId: problem.id,
          solutionIndex: Number(solutionIndex) % 100000,
          content,
          author: String(author),
        },
        update: {
          content,
          author: String(author),
        },
      });

      // Generate and store solution embedding (spec: 子2)
      try {
        const truncated = content.length > 2000 ? content.slice(0, 2000) : content;
        const solVec = await this.vectorService.embedText(truncated);
        await this.vectorService.setSolutionVector(upserted.id, solVec);
      } catch (embedErr: any) {
        this.logger.warn(`Solution embedding failed for ${sourceId}: ${embedErr?.message || embedErr}`);
      }
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
      throw new ConflictException(
        `Platform ${platform} already has a running bulk crawl (jobId=${existing.id}). Cancel it first or wait for completion.`
      );
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
              this.summarizeUnprocessed(platform, job.id)
                .then((n) => this.logger.log(`Auto-summarize done for bulk crawl ${job.id}: ${n} problems summarized`))
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
    jobId: string; platform: string; embedTotal: number; embedDone: number;
    done: boolean; summary?: any;
  }> {
    const job = await this.prisma.crawlJob.findUnique({ where: { id: jobId } });
    if (!job) throw new NotFoundException(`CrawlJob ${jobId} not found`);

    const embedTotal = job.embedTotal ?? 0;
    const embedDone = job.embedDone ?? 0;
    return {
      jobId: job.id,
      platform: job.platform,
      embedTotal,
      embedDone,
      done: embedTotal > 0 && embedDone >= embedTotal,
      summary: job.summary as any,
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
      .then(async (n) => {
        this.logger.log(`Summarization done for ${platform}: ${n} problems processed`);
        await this.prisma.crawlJob.update({
          where: { id: embedJob.id },
          data: { status: 'completed', finishedAt: new Date(), summary: { embedded: n } },
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
  async summarizeUnprocessed(platform: string, jobId?: string): Promise<number> {
    // Skip if no LLM API key configured — summarization requires DeepSeek
    const apiKey = process.env.DEEPSEEK_API_KEY || '';
    if (!apiKey || apiKey === 'sk-placeholder') {
      this.logger.log('No DeepSeek API key configured, skipping summarization and embedding');
      if (jobId) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedTotal: 0, embedDone: 0, status: 'completed', finishedAt: new Date() },
        }).catch(() => {});
      }
      return 0;
    }

    // Count total unprocessed (for progress tracking)
    const totalUnprocessed = await this.prisma.problem.count({
      where: {
        sourcePlatform: platform as any,
        OR: [{ solutionSummary: null }, { solutionSummary: '' }],
      },
    });

    if (totalUnprocessed === 0) {
      this.logger.log(`No unprocessed problems for ${platform}`);
      if (jobId) {
        await this.prisma.crawlJob.update({
          where: { id: jobId },
          data: { embedTotal: 0, embedDone: 0 },
        });
      }
      return 0;
    }

    // Set embedTotal on CrawlJob
    if (jobId) {
      await this.prisma.crawlJob.update({
        where: { id: jobId },
        data: { embedTotal: totalUnprocessed, embedDone: 0 },
      });
    }

    let count = 0;
    const batchSize = 50; // Fetch in batches to avoid memory issues
    let offset = 0;

    while (true) {
      const unprocessed = await this.prisma.problem.findMany({
        where: {
          sourcePlatform: platform as any,
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

            // Generate and store vector embeddings (parent + content)
            try {
              const [parentVec, contentVec] = await Promise.all([
                this.vectorService.embedText(summary),
                this.vectorService.embedText(p.fullContent || ''),
              ]);
              await this.vectorService.setProblemVectors(p.id, parentVec, contentVec);
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
      }

      // If we got fewer than batchSize, we've processed everything
      if (unprocessed.length < batchSize) break;
      // Don't increment offset — we're deleting processed items, so offset stays 0
    }

    return count;
  }

  private async callDeepSeekSummarize(title: string, content: string, difficultyRaw: string): Promise<string | null> {
    const apiKey = process.env.DEEPSEEK_API_KEY || '';
    const baseUrl = process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com';
    if (!apiKey || apiKey === 'sk-placeholder') {
      // No valid API key configured — skip summarization entirely.
      // Frontend shows "暂无题解总结（配置 DeepSeek API Key 后可获得 AI 生成的题解总结）"
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

    const resp = await fetch(`${baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${apiKey}` },
      body: JSON.stringify({
        model: 'deepseek-v4-flash',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
        max_tokens: 600,
      }),
    });

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`DeepSeek API error ${resp.status}: ${errText.slice(0, 200)}`);
    }

    const data: any = await resp.json();
    return data?.choices?.[0]?.message?.content || null;
  }
}
