import {
  Controller,
  Get,
  Post,
  Patch,
  Delete,
  Body,
  Param,
  Query,
  UseGuards,
} from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBearerAuth } from '@nestjs/swagger';
import { UserService } from './user.service';
import { UserQueryDto } from './dto/user-query.dto';
import { UpdateUserDto } from './dto/update-user.dto';
import { BindPlatformDto } from './dto/bind-platform.dto';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { Platform } from '@prisma/client';

@ApiTags('Users')
@Controller('api/users')
@ApiBearerAuth()
export class UserController {
  constructor(private readonly userService: UserService) {}

  @Get()
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: 'List all users (admin only)' })
  findAll(@Query() query: UserQueryDto) {
    return this.userService.findAll(query);
  }

  @Get(':id')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Get user by ID' })
  findById(@Param('id') id: string) {
    return this.userService.findById(id);
  }

  @Patch(':id')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Update user profile (self or admin)' })
  update(
    @Param('id') id: string,
    @Body() dto: UpdateUserDto,
    @CurrentUser() currentUser: { userId: string; username: string; role: string },
  ) {
    return this.userService.update(id, dto, {
      userId: currentUser.userId,
      role: currentUser.role,
    });
  }

  @Delete(':id')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  @ApiOperation({ summary: 'Soft-delete a user (admin only)' })
  softDelete(@Param('id') id: string) {
    return this.userService.softDelete(id);
  }

  @Post(':id/platforms')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Bind an OJ platform account to user' })
  bindPlatform(
    @Param('id') id: string,
    @Body() dto: BindPlatformDto,
  ) {
    return this.userService.bindPlatform(id, dto);
  }

  @Delete(':id/platforms/:platform')
  @UseGuards(JwtAuthGuard)
  @ApiOperation({ summary: 'Unbind an OJ platform account from user' })
  unbindPlatform(
    @Param('id') id: string,
    @Param('platform') platform: Platform,
  ) {
    return this.userService.unbindPlatform(id, platform);
  }
}
