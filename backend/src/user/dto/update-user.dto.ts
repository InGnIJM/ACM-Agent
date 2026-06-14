import { ApiPropertyOptional } from '@nestjs/swagger';
import { IsOptional, IsString, IsEmail, MaxLength } from 'class-validator';

export class UpdateUserDto {
  @ApiPropertyOptional({ description: 'Display nickname', maxLength: 100 })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  nickname?: string;

  @ApiPropertyOptional({ description: 'Email address', maxLength: 200 })
  @IsOptional()
  @IsEmail()
  @MaxLength(200)
  email?: string;

  @ApiPropertyOptional({ description: 'Real name', maxLength: 50 })
  @IsOptional()
  @IsString()
  @MaxLength(50)
  realName?: string;

  @ApiPropertyOptional({ description: 'Student ID', maxLength: 30 })
  @IsOptional()
  @IsString()
  @MaxLength(30)
  studentId?: string;

  @ApiPropertyOptional({ description: 'Department name', maxLength: 100 })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  department?: string;

  @ApiPropertyOptional({ description: 'Major', maxLength: 100 })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  major?: string;

  @ApiPropertyOptional({ description: 'Class name', maxLength: 50 })
  @IsOptional()
  @IsString()
  @MaxLength(50)
  className?: string;

  @ApiPropertyOptional({ description: 'Current grade', maxLength: 10 })
  @IsOptional()
  @IsString()
  @MaxLength(10)
  grade?: string;

  @ApiPropertyOptional({ description: 'Enrollment year' })
  @IsOptional()
  enrollmentYear?: number;

  @ApiPropertyOptional({ description: 'Feishu Open ID' })
  @IsOptional()
  @IsString()
  feishuOpenId?: string;

  @ApiPropertyOptional({ description: 'QQ number' })
  @IsOptional()
  @IsString()
  qqNumber?: string;

  @ApiPropertyOptional({ description: 'Push channel preferences (JSON)' })
  @IsOptional()
  pushChannels?: Record<string, unknown>;
}
