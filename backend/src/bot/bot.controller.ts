import { Controller, Get, Patch, Post, Body, Req, UseGuards } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { Request } from 'express';
import { PushService } from './bot.service';
import { BotConfigDto } from './dto/bot-config.dto';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { BotChannel } from '@prisma/client';

@ApiTags('Bot')
@ApiBearerAuth()
@Controller('api/bot')
export class BotController {
  constructor(private readonly pushService: PushService) {}

  @Get('configs')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Get current user bot configs' })
  async getConfigs(@Req() req: Request) {
    const userId = (req.user as { id: string }).id;
    return this.pushService.getConfigs(userId);
  }

  @Patch('configs')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Upsert a bot config for current user' })
  async upsertConfig(@Req() req: Request, @Body() dto: BotConfigDto) {
    const userId = (req.user as { id: string }).id;
    return this.pushService.upsertConfig(userId, dto);
  }

  @Post('push/daily')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: '[Admin] Manually trigger daily report push' })
  async triggerDaily(@Body() body: { channel: BotChannel; targetId: string }) {
    const data = {
      date: new Date().toISOString().slice(0, 10),
      stats: { totalSubmits: 0, totalAc: 0, acRate: '0%' },
      ranking: [],
    };
    await this.pushService.sendDailyReport(body.channel, body.targetId, data);
    return { message: 'Daily report push triggered' };
  }

  @Post('push/weekly')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: '[Admin] Manually trigger weekly report push' })
  async triggerWeekly(@Body() body: { channel: BotChannel; targetId: string }) {
    const data = {
      weekLabel: '本周',
      totalAc: 0,
      totalSubmits: 0,
      acRate: '0%',
      activeUsers: 0,
      strengths: [],
      weaknesses: [],
      topUsers: [],
    };
    await this.pushService.sendWeeklyReport(body.channel, body.targetId, data);
    return { message: 'Weekly report push triggered' };
  }

  @Post('test')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Test push to current user' })
  async testPush(@Req() req: Request, @Body() body: { channel: BotChannel }) {
    const userId = (req.user as { id: string }).id;
    const data = {
      date: new Date().toISOString().slice(0, 10),
      stats: { totalSubmits: 0, totalAc: 0, acRate: '0%' },
      ranking: [],
    };
    await this.pushService.sendDailyReport(body.channel, userId, data);
    return { message: 'Test push sent' };
  }
}
