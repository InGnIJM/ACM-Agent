import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsEnum, IsString, IsOptional, MaxLength } from 'class-validator';
import { Platform } from '@prisma/client';

export class BindPlatformDto {
  @ApiProperty({ description: 'Platform to bind', enum: Platform })
  @IsEnum(Platform)
  platform: Platform;

  @ApiProperty({ description: 'Platform user ID', maxLength: 100 })
  @IsString()
  @MaxLength(100)
  platformUid: string;

  @ApiPropertyOptional({ description: 'Platform username', maxLength: 100 })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  platformUsername?: string;
}
