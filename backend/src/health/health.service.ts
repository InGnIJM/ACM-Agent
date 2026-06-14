import { Injectable } from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { readFileSync } from 'fs';
import { join } from 'path';

@Injectable()
export class HealthService {
  private readonly version: string;

  constructor(private readonly prisma: PrismaService) {
    try {
      const pkg = JSON.parse(
        readFileSync(join(__dirname, '../../package.json'), 'utf-8'),
      );
      this.version = pkg.version || '0.0.1';
    } catch {
      this.version = '0.0.1';
    }
  }

  async check() {
    try {
      await this.prisma.$queryRaw`SELECT 1`;
      return {
        status: 'ok',
        database: 'connected',
        timestamp: new Date().toISOString(),
        version: this.version,
      };
    } catch {
      return {
        status: 'error',
        database: 'disconnected',
        timestamp: new Date().toISOString(),
        version: this.version,
      };
    }
  }
}
