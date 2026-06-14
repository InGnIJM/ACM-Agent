import {
  Controller,
  Post,
  Get,
  Body,
  Param,
  UseGuards,
  HttpCode,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { PythonService } from './python.service';
import { TriggerCrawlDto } from './dto/trigger-crawl.dto';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { Logger } from '@nestjs/common';

@ApiTags('Crawler')
@ApiBearerAuth()
@Controller('api/crawler')
export class CrawlerController {
  private readonly logger = new Logger(CrawlerController.name);

  constructor(private readonly pythonService: PythonService) {}

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
  @HttpCode(202)
  @ApiOperation({ summary: 'Trigger crawl task (problems, user, records, solutions, import)' })
  async triggerProblemCrawl(@Body() dto: TriggerCrawlDto): Promise<{ accepted: boolean; platform?: string; action?: string }> {
    this.logger.log(`Triggering crawl: platform=${dto.platform || 'all'}, action=${dto.action}, uid=${dto.uid || 'none'}, tags=${dto.tags || 'none'}, count=${dto.count ?? 50}`);

    // Map platform to its crawler script
    const platformScripts: Record<string, string> = {
      luogu: 'crawlers/luogu.py',
      leetcode: 'crawlers/leetcode.py',
      codeforces: 'crawlers/codeforces.py',
      atcoder: 'crawlers/atcoder.py',
      nowcoder: 'crawlers/nowcoder.py',
    };

    const script = dto.platform ? platformScripts[dto.platform] : null;
    if (!script) {
      this.logger.warn(`Unknown or missing platform: ${dto.platform}`);
      return { accepted: false, platform: dto.platform, action: dto.action };
    }

    // Pass all params as JSON via --input (same format all platform CLIs expect)
    const params = {
      action: dto.action,
      uid: dto.uid,
      tags: dto.tags,
      count: dto.count ?? 50,
    };

    this.pythonService
      .execute(script, params)
      .then((result) => this.logger.log(`Crawl completed for ${dto.platform}: ${JSON.stringify(result)}`))
      .catch((err) => this.logger.error(`Crawl failed for ${dto.platform}: ${err.message}`));
    return { accepted: true, platform: dto.platform, action: dto.action };
  }

  @Post('login/:platform')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @HttpCode(202)
  @ApiOperation({ summary: 'Open browser login page for a platform' })
  async loginPlatform(@Param('platform') platform: string): Promise<{ accepted: boolean; platform: string }> {
    this.logger.log(`Opening login page for platform: ${platform}`);

    // Fire-and-forget: spawn Python script that opens browser for manual login
    this.pythonService
      .execute('crawlers/luogu_login.py', { platform })
      .then((result) => this.logger.log(`Login script completed: ${JSON.stringify(result)}`))
      .catch((err) => this.logger.error(`Login script failed: ${err.message}`));

    return { accepted: true, platform };
  }

  @Get('cookies/:platform')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Check cookie status for a platform' })
  checkCookies(@Param('platform') platform: string): { platform: string; hasCookies: boolean } {
    const fs = require('fs');
    const path = `../python/data/cookies/${platform}.json`;
    let hasCookies = false;
    try {
      const data = JSON.parse(fs.readFileSync(path, 'utf-8'));
      hasCookies = Array.isArray(data) && data.length > 0;
    } catch {}
    return { platform, hasCookies };
  }

  @Get('logs')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: 'Recent crawl logs (placeholder)' })
  getRecentLogs(): { message: string } {
    return { message: 'Crawl logs endpoint is a placeholder. Query push_logs for history.' };
  }
}
