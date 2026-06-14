import {
  Injectable,
  ConflictException,
  NotFoundException,
} from '@nestjs/common';
import { PrismaService } from '../common/prisma/prisma.service';

const ACM_MAX_TEAM_SIZE = 3;

@Injectable()
export class TeamService {
  constructor(private readonly prisma: PrismaService) {}

  /** Create a new team and add the creator as the first member. */
  async create(name: string, creatorId: string) {
    const team = await this.prisma.team.create({
      data: {
        name,
        createdBy: creatorId,
      },
    });

    await this.prisma.teamMember.create({
      data: {
        teamId: team.id,
        userId: creatorId,
      },
    });

    return this.findById(team.id);
  }

  /** List all active teams with member count. */
  async findAll() {
    const teams = await this.prisma.team.findMany({
      where: { status: 'active' },
      include: {
        _count: { select: { members: true } },
        creator: { select: { id: true, username: true, nickname: true } },
      },
      orderBy: { createdAt: 'desc' },
    });

    return teams.map((t) => ({
      id: t.id,
      name: t.name,
      status: t.status,
      createdBy: t.createdBy,
      creator: t.creator,
      memberCount: t._count.members,
      createdAt: t.createdAt,
      updatedAt: t.updatedAt,
    }));
  }

  /** Get a single team with members and their profiles. */
  async findById(id: string) {
    const team = await this.prisma.team.findUnique({
      where: { id },
      include: {
        creator: { select: { id: true, username: true, nickname: true } },
        members: {
          include: {
            user: {
              select: {
                id: true,
                username: true,
                nickname: true,
                studentId: true,
                department: true,
                major: true,
                profile: true,
              },
            },
          },
          orderBy: { joinedAt: 'asc' },
        },
      },
    });

    if (!team) {
      throw new NotFoundException(`Team ${id} not found`);
    }

    return team;
  }

  /** Add a member to a team. */
  async addMember(teamId: string, userId: string) {
    const team = await this.prisma.team.findUnique({
      where: { id: teamId },
      include: { _count: { select: { members: true } } },
    });

    if (!team) {
      throw new NotFoundException(`Team ${teamId} not found`);
    }

    if (team.status !== 'active') {
      throw new ConflictException('Cannot add members to an archived team');
    }

    const existing = await this.prisma.teamMember.findUnique({
      where: { teamId_userId: { teamId, userId } },
    });
    if (existing) {
      throw new ConflictException('User is already a member of this team');
    }

    if (team._count.members >= ACM_MAX_TEAM_SIZE) {
      throw new ConflictException(
        `Team is full (max ${ACM_MAX_TEAM_SIZE} members for ACM)`,
      );
    }

    const member = await this.prisma.teamMember.create({
      data: { teamId, userId },
      include: {
        user: {
          select: {
            id: true,
            username: true,
            nickname: true,
            studentId: true,
            department: true,
            major: true,
            profile: true,
          },
        },
      },
    });

    return member;
  }

  /** Remove a member from a team. */
  async removeMember(teamId: string, userId: string) {
    const member = await this.prisma.teamMember.findUnique({
      where: { teamId_userId: { teamId, userId } },
    });

    if (!member) {
      throw new NotFoundException(
        `User ${userId} is not a member of team ${teamId}`,
      );
    }

    await this.prisma.teamMember.delete({
      where: { id: member.id },
    });

    return { deleted: true };
  }

  /** Archive a team (soft-archive via status change). */
  async archive(teamId: string) {
    const team = await this.prisma.team.findUnique({ where: { id: teamId } });
    if (!team) {
      throw new NotFoundException(`Team ${teamId} not found`);
    }

    if (team.status === 'archived') {
      return team;
    }

    return this.prisma.team.update({
      where: { id: teamId },
      data: { status: 'archived' },
    });
  }
}
