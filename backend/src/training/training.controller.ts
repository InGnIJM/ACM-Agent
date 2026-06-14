import { Controller, Get, Post, Param, UseGuards } from '@nestjs/common';
import { ApiTags, ApiBearerAuth, ApiOperation } from '@nestjs/swagger';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { TrainingService } from './training.service';

@ApiTags('Training')
@Controller('api/training')
export class TrainingController {
  constructor(private readonly trainingService: TrainingService) {}

  @Get('plans/:userId')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: '获取用户当前训练计划' })
  async getPlan(@Param('userId') userId: string) {
    return this.trainingService.getPlan(userId);
  }

  @Post('plans/:userId/generate')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: '生成训练计划' })
  async generatePlan(@Param('userId') userId: string) {
    return this.trainingService.generatePlan(userId);
  }

  @Get('recommend')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: '快速推荐题目' })
  async getRecommend() {
    return this.trainingService.getRecommend();
  }
}
