import { Module } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { BotController } from './bot.controller';
import { PushService } from './bot.service';
import { BotScheduler } from './bot.scheduler';

@Module({
  imports: [ScheduleModule.forRoot()],
  controllers: [BotController],
  providers: [PushService, BotScheduler],
  exports: [PushService],
})
export class BotModule {}
