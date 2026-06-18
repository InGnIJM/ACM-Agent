import { Global, Module } from '@nestjs/common';
import { VectorService } from './vector.service';

@Global()
@Module({
  providers: [VectorService],
  exports: [VectorService],
})
export class VectorModule {}
