import {
  Injectable,
  NotFoundException,
  ConflictException,
  ForbiddenException,
} from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';
import { UserQueryDto } from './dto/user-query.dto';
import { UpdateUserDto } from './dto/update-user.dto';
import { BindPlatformDto } from './dto/bind-platform.dto';
import { Platform, Prisma } from '@prisma/client';

export interface PaginatedResult<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
}

@Injectable()
export class UserService {
  constructor(private readonly prisma: PrismaService) {}

  async findAll(query: UserQueryDto): Promise<PaginatedResult<Record<string, unknown>>> {
    const page = query.page ?? 1;
    const limit = query.limit ?? 20;
    const skip = (page - 1) * limit;

    const where: Prisma.UserWhereInput = {};

    if (query.role) {
      where.role = query.role;
    }

    if (query.platform) {
      where.platformAccounts = {
        some: { platform: query.platform },
      };
    }

    if (query.search) {
      const trimmedSearch = query.search.trim();
      where.OR = [
        { username: { contains: trimmedSearch } },
        { nickname: { contains: trimmedSearch } },
        { studentId: { contains: trimmedSearch } },
      ];
    }

    const [data, total] = await Promise.all([
      this.prisma.user.findMany({
        where,
        skip,
        take: limit,
        orderBy: { createdAt: 'desc' },
        select: {
          id: true,
          username: true,
          role: true,
          nickname: true,
          email: true,
          realName: true,
          studentId: true,
          department: true,
          major: true,
          className: true,
          grade: true,
          enrollmentYear: true,
          feishuOpenId: true,
          qqNumber: true,
          pushChannels: true,
          createdAt: true,
          updatedAt: true,
        },
      }),
      this.prisma.user.count({ where }),
    ]);

    return { data, total, page, limit };
  }

  async findById(id: string) {
    const user = await this.prisma.user.findUnique({
      where: { id },
    });

    if (!user) {
      throw new NotFoundException(`User ${id} not found`);
    }

    const { passwordHash, deletedAt, ...safeUser } = user;
    return safeUser;
  }

  async update(
    id: string,
    dto: UpdateUserDto,
    actor: { userId: string; role: string },
  ) {
    const user = await this.prisma.user.findUnique({ where: { id } });
    if (!user) {
      throw new NotFoundException(`User ${id} not found`);
    }

    // Permission check: admin or self
    if (actor.role !== 'admin' && actor.userId !== id) {
      throw new ForbiddenException('You can only update your own profile');
    }

    // Strip undefined fields and ensure passwordHash/username/role are not in dto
    const updateData: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(dto)) {
      if (value !== undefined && !['passwordHash', 'username', 'role'].includes(key)) {
        updateData[key] = value;
      }
    }

    updateData.updatedBy = actor.userId;

    const updated = await this.prisma.user.update({
      where: { id },
      data: updateData,
    });

    const { passwordHash, deletedAt, ...safeUser } = updated;
    return safeUser;
  }

  async softDelete(id: string) {
    const user = await this.prisma.user.findUnique({ where: { id } });
    if (!user) {
      throw new NotFoundException(`User ${id} not found`);
    }

    await this.prisma.user.update({
      where: { id },
      data: { deletedAt: new Date() },
    });
  }

  async bindPlatform(userId: string, dto: BindPlatformDto) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) {
      throw new NotFoundException(`User ${userId} not found`);
    }

    // Check platform+platformUid uniqueness
    const existing = await this.prisma.platformAccount.findFirst({
      where: {
        platform: dto.platform,
        platformUid: dto.platformUid,
      },
    });

    if (existing) {
      throw new ConflictException(
        `Platform ${dto.platform} with UID ${dto.platformUid} is already bound`,
      );
    }

    return this.prisma.platformAccount.create({
      data: {
        userId,
        platform: dto.platform,
        platformUid: dto.platformUid,
        platformUsername: dto.platformUsername ?? dto.platformUid,
      },
    });
  }

  async unbindPlatform(userId: string, platform: Platform) {
    await this.prisma.platformAccount.deleteMany({
      where: {
        userId,
        platform,
      },
    });
  }
}
