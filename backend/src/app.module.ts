import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { PrismaModule } from './common/prisma/prisma.module';
import { HealthModule } from './health/health.module';
import { AuthModule } from './auth/auth.module';
import { UserModule } from './user/user.module';
import { ProblemModule } from './problem/problem.module';
import { RecordModule } from './record/record.module';
import { ProfileModule } from './profile/profile.module';
import { TrainingModule } from './training/training.module';
import { MatchingModule } from './matching/matching.module';
import { TeamModule } from './team/team.module';
import { BotModule } from './bot/bot.module';
import { CrawlerModule } from './crawler/crawler.module';
import { TaskModule } from './task/task.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: ['.env', '.env.local'],
    }),
    PrismaModule,
    HealthModule,
    AuthModule,
    UserModule,
    ProblemModule,
    RecordModule,
    ProfileModule,
    TrainingModule,
    MatchingModule,
    TeamModule,
    BotModule,
    CrawlerModule,
    TaskModule,
  ],
})
export class AppModule {}
