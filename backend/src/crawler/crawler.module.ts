import { Module } from '@nestjs/common';
import { CrawlerController } from './crawler.controller';
import { PythonService } from './python.service';

@Module({
  controllers: [CrawlerController],
  providers: [PythonService],
  exports: [PythonService],
})
export class CrawlerModule {}
