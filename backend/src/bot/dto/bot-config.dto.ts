import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import {
  IsBoolean,
  IsEnum,
  IsOptional,
  IsString,
  MaxLength,
} from 'class-validator';
import { BotChannel } from '@prisma/client';

export class BotConfigDto {
  @ApiProperty({ description: 'Push channel', enum: BotChannel })
  @IsEnum(BotChannel)
  channel: BotChannel;

  @ApiPropertyOptional({ description: 'Webhook URL (required for feishu)', maxLength: 500 })
  @IsOptional()
  @IsString()
  @MaxLength(500)
  webhookUrl?: string;

  @ApiPropertyOptional({ description: 'Enable push', default: true })
  @IsOptional()
  @IsBoolean()
  enabled?: boolean;

  @ApiPropertyOptional({ description: 'Custom cron expression', maxLength: 50 })
  @IsOptional()
  @IsString()
  @MaxLength(50)
  scheduleCron?: string;
}
