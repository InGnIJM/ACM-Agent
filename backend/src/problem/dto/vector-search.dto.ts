import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsString, IsInt, IsOptional, Min, Max } from 'class-validator';
import { Type } from 'class-transformer';

export class VectorSearchDto {
  @ApiProperty({ description: 'Natural-language search query', example: 'dynamic programming on trees' })
  @IsString()
  query: string;

  @ApiPropertyOptional({ description: 'Number of results', default: 20, minimum: 1, maximum: 100 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100)
  topK?: number;

  @ApiPropertyOptional({ description: 'Filter by platform', example: 'luogu' })
  @IsOptional()
  @IsString()
  platform?: string;

  @ApiPropertyOptional({ description: 'Filter by tags (comma-separated)', example: 'dp,tree' })
  @IsOptional()
  @IsString()
  tags?: string;

  @ApiPropertyOptional({ description: 'Minimum difficulty (1-10)' })
  @IsOptional()
  @Type(() => Number)
  difficultyMin?: number;

  @ApiPropertyOptional({ description: 'Maximum difficulty (1-10)' })
  @IsOptional()
  @Type(() => Number)
  difficultyMax?: number;
}
