import { IsString, IsInt, IsOptional, IsArray, IsBoolean, Min, Max } from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class BulkCrawlDto {
  @ApiProperty({ description: 'Platform to crawl', example: 'luogu' })
  @IsString()
  platform: string;

  @ApiPropertyOptional({ description: 'Problem tag filter', example: 'P' })
  @IsOptional()
  @IsString()
  tags?: string;

  @ApiPropertyOptional({ description: 'Max problems to fetch', default: 100, maximum: 100000 })
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100000)
  count?: number = 100;

  @ApiPropertyOptional({
    description: 'Phases to execute (list, detail, solutions)',
    example: ['list', 'detail', 'solutions'],
  })
  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  phases?: string[];

  @ApiPropertyOptional({ description: 'Skip already-imported problems', default: true })
  @IsOptional()
  @IsBoolean()
  skipExisting?: boolean = true;
}
