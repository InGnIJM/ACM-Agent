import { ApiProperty } from '@nestjs/swagger';

export class TokenResponseDto {
  @ApiProperty({ description: 'JWT access token' })
  access_token: string;

  @ApiProperty({ description: 'JWT refresh token' })
  refresh_token: string;

  @ApiProperty({ description: 'Token expiration time in seconds' })
  expires_in: number;

  @ApiProperty({ description: 'Token type (Bearer)' })
  token_type: string;
}
