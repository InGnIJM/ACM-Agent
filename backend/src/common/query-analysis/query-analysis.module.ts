import { Global, Module } from '@nestjs/common';
import { QueryAnalysisService } from './query-analysis.service';

@Global()
@Module({
  providers: [QueryAnalysisService],
  exports: [QueryAnalysisService],
})
export class QueryAnalysisModule {}
