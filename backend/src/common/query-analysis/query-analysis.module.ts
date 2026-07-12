import { Global, Module } from '@nestjs/common';
import { QueryAnalysisService } from './query-analysis.service';
import { QueryExpansionService } from './query-expansion.service';

@Global()
@Module({
  providers: [QueryAnalysisService, QueryExpansionService],
  exports: [QueryAnalysisService, QueryExpansionService],
})
export class QueryAnalysisModule {}
