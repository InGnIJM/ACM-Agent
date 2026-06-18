import { Module } from '@nestjs/common';
import { CrawlerController } from './crawler.controller';
import { PythonService } from './python.service';
import { PrismaModule } from '../common/prisma/prisma.module';

@Module({
  imports: [PrismaModule],
  controllers: [CrawlerController],
  providers: [PythonService],
  exports: [PythonService],
})
export class CrawlerModule {}
