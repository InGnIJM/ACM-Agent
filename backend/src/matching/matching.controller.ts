import { Controller, Get, Post, Param, UseGuards } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { MatchingService } from './matching.service';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';

@ApiTags('Matching')
@Controller('api/matching')
export class MatchingController {
  constructor(private readonly matching: MatchingService) {}

  @Post('recommend/:userId')
  @UseGuards(JwtAuthGuard)
  recommend(@Param('userId') userId: string) {
    return this.matching.recommend(userId);
  }

  @Get('compatibility/:userId/:targetId')
  @UseGuards(JwtAuthGuard)
  getCompatibility(
    @Param('userId') userId: string,
    @Param('targetId') targetId: string,
  ) {
    return this.matching.getCompatibility(userId, targetId);
  }
}
