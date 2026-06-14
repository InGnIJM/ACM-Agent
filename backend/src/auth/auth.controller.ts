import {
  Controller,
  Post,
  Get,
  Body,
  HttpCode,
  UseGuards,
} from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { AuthService } from './auth.service';
import { RegisterDto } from './dto/register.dto';
import { LoginDto } from './dto/login.dto';
import { RefreshTokenDto } from './dto/refresh-token.dto';
import { TokenResponseDto } from './dto/token-response.dto';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';

@ApiTags('Auth')
@Controller('api/auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Post('register')
  @HttpCode(201)
  register(@Body() dto: RegisterDto): Promise<TokenResponseDto> {
    return this.auth.register(dto);
  }

  @Post('login')
  @HttpCode(201)
  login(@Body() dto: LoginDto): Promise<TokenResponseDto> {
    return this.auth.login(dto);
  }

  @Post('refresh')
  @HttpCode(201)
  refresh(@Body() dto: RefreshTokenDto): Promise<{ access_token: string; token_type: string; expires_in: number }> {
    return this.auth.refreshToken(dto.refresh_token);
  }

  @Get('me')
  @UseGuards(JwtAuthGuard)
  getMe(@CurrentUser() user: { userId: string; username: string; role: string }) {
    return this.auth.getProfile(user.userId);
  }
}
