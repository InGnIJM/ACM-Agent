import { Global, Module } from '@nestjs/common';
import { RerankService } from './rerank.service';

@Global()
@Module({
  providers: [RerankService],
  exports: [RerankService],
})
export class RerankModule {}
