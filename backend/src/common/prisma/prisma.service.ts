import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

const softDeleteModels: string[] = [
  'User',
  'PlatformAccount',
  'Problem',
  'ProblemSolution',
  'UserProfile',
  'TrainingPlan',
  'Team',
  'BotConfig',
];

@Injectable()
export class PrismaService
  extends PrismaClient
  implements OnModuleInit, OnModuleDestroy
{
  async onModuleInit() {
    await this.$connect();

    this.$use(async (params, next) => {
      if (
        (params.action === 'findUnique' ||
          params.action === 'findFirst' ||
          params.action === 'findMany') &&
        params.model &&
        softDeleteModels.includes(params.model)
      ) {
        if (!params.args.where) {
          params.args.where = {};
        }
        if (params.args.where.deletedAt === undefined) {
          params.args.where.deletedAt = null;
        }
      }
      return next(params);
    });
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
