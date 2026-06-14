import {
  Injectable,
  ConflictException,
  UnauthorizedException,
  BadRequestException,
} from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { RegisterDto } from './dto/register.dto';
import { LoginDto } from './dto/login.dto';
import { TokenResponseDto } from './dto/token-response.dto';

@Injectable()
export class AuthService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly jwt: JwtService,
  ) {}

  async register(dto: RegisterDto): Promise<TokenResponseDto> {
    if (dto.password.length < 6) {
      throw new BadRequestException('Password must be at least 6 characters');
    }

    const existing = await this.prisma.user.findUnique({
      where: { username: dto.username },
    });
    if (existing) {
      throw new ConflictException('Username already exists');
    }

    const passwordHash = await bcrypt.hash(dto.password, 10);

    const user = await this.prisma.user.create({
      data: {
        username: dto.username,
        passwordHash,
        nickname: dto.nickname,
        studentId: dto.studentId,
      },
    });

    return this.generateTokens(user.id, user.username, user.role);
  }

  async login(dto: LoginDto): Promise<TokenResponseDto> {
    const user = await this.prisma.user.findUnique({
      where: { username: dto.username },
    });
    if (!user) {
      throw new UnauthorizedException('Invalid credentials');
    }

    const isMatch = await bcrypt.compare(dto.password, user.passwordHash);
    if (!isMatch) {
      throw new UnauthorizedException('Invalid credentials');
    }

    return this.generateTokens(user.id, user.username, user.role);
  }

  async getProfile(userId: string) {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
    });
    if (!user) {
      return null;
    }
    const { passwordHash, deletedAt, ...safeUser } = user;
    return safeUser;
  }

  async refreshToken(token: string) {
    try {
      const payload = this.jwt.verify<{ sub: string; username: string; role: string }>(
        token,
        {
          secret: process.env.JWT_REFRESH_SECRET || 'dev-refresh-secret',
        },
      );

      const access_token = this.jwt.sign(
        { sub: payload.sub, username: payload.username, role: payload.role },
        { expiresIn: '2h' },
      );

      return {
        access_token,
        token_type: 'Bearer',
        expires_in: 7200,
      };
    } catch {
      throw new UnauthorizedException('Invalid refresh token');
    }
  }

  private generateTokens(
    sub: string,
    username: string,
    role: string,
  ): TokenResponseDto {
    const payload = { sub, username, role };

    const access_token = this.jwt.sign(payload, { expiresIn: '2h' });
    const refresh_token = this.jwt.sign(payload, {
      secret: process.env.JWT_REFRESH_SECRET || 'dev-refresh-secret',
      expiresIn: '7d',
    });

    return {
      access_token,
      refresh_token,
      expires_in: 7200,
      token_type: 'Bearer',
    };
  }
}
