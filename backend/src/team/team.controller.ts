import {
  Controller,
  Get,
  Post,
  Delete,
  Patch,
  Body,
  Param,
  HttpCode,
  UseGuards,
} from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { TeamService } from './team.service';
import { CreateTeamDto } from './dto/create-team.dto';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';

@ApiTags('Teams')
@Controller('api/teams')
export class TeamController {
  constructor(private readonly team: TeamService) {}

  @Post()
  @HttpCode(201)
  @UseGuards(JwtAuthGuard)
  create(
    @Body() dto: CreateTeamDto,
    @CurrentUser() user: { userId: string },
  ) {
    return this.team.create(dto.name, user.userId);
  }

  @Get()
  findAll() {
    return this.team.findAll();
  }

  @Get(':id')
  findById(@Param('id') id: string) {
    return this.team.findById(id);
  }

  @Post(':id/members')
  @HttpCode(201)
  @UseGuards(JwtAuthGuard)
  addMember(
    @Param('id') id: string,
    @Body('userId') userId: string,
  ) {
    return this.team.addMember(id, userId);
  }

  @Delete(':id/members/:userId')
  @HttpCode(200)
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  removeMember(
    @Param('id') id: string,
    @Param('userId') userId: string,
  ) {
    return this.team.removeMember(id, userId);
  }

  @Patch(':id/archive')
  @HttpCode(200)
  @UseGuards(JwtAuthGuard)
  archive(@Param('id') id: string) {
    return this.team.archive(id);
  }
}
