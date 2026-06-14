import { ApiPropertyOptional } from '@nestjs/swagger';
import { IsString, IsOptional, IsInt, Min, Max } from 'class-validator';
import { Type } from 'class-transformer';

export class TriggerCrawlDto {
  @ApiPropertyOptional({ description: 'Platform to crawl from (e.g. luogu, codeforces, leetcode, atcoder, nowcoder)' })
  @IsOptional()
  @IsString()
  platform?: string;

  @ApiPropertyOptional({ description: 'Crawl action: fetch_problems, fetch_user, fetch_records, fetch_solutions, import' })
  @IsOptional()
  @IsString()
  action?: string;

  @ApiPropertyOptional({ description: 'Target user ID / handle for user-scoped actions' })
  @IsOptional()
  @IsString()
  uid?: string;

  @ApiPropertyOptional({ description: 'Tag filter for problem crawling (comma-separated string)' })
  @IsOptional()
  @IsString()
  tags?: string;

  @ApiPropertyOptional({ description: 'Max number of items to fetch', default: 50 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(1000)
  count?: number;
}
