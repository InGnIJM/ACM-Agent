import { Test, TestingModule } from '@nestjs/testing';
import { TeamService } from '../src/team/team.service';
import { PrismaService } from '../src/common/prisma/prisma.service';
import { ConflictException, NotFoundException } from '@nestjs/common';

describe('TeamService', () => {
  let service: TeamService;
  let prisma: {
    team: {
      create: jest.Mock;
      findMany: jest.Mock;
      findUnique: jest.Mock;
      update: jest.Mock;
    };
    teamMember: {
      create: jest.Mock;
      findUnique: jest.Mock;
      delete: jest.Mock;
    };
  };

  const mockTeam = {
    id: 'team-1',
    name: 'Team Alpha',
    status: 'active',
    createdBy: 'user-1',
    createdAt: new Date('2025-01-01'),
    updatedAt: new Date('2025-01-01'),
    creator: { id: 'user-1', username: 'alice', nickname: 'Alice' },
    _count: { members: 1 },
  };

  const mockMember = {
    id: 'member-1',
    teamId: 'team-1',
    userId: 'user-2',
    joinedAt: new Date('2025-01-02'),
    user: {
      id: 'user-2',
      username: 'bob',
      nickname: 'Bob',
      studentId: 'S12345',
      department: 'CS',
      major: 'SE',
      profile: null,
    },
  };

  const mockTeamDetail = {
    ...mockTeam,
    members: [
      {
        id: 'member-1',
        teamId: 'team-1',
        userId: 'user-1',
        joinedAt: new Date('2025-01-01'),
        user: {
          id: 'user-1',
          username: 'alice',
          nickname: 'Alice',
          studentId: 'S11111',
          department: 'CS',
          major: 'SE',
          profile: null,
        },
      },
    ],
  };

  beforeEach(async () => {
    prisma = {
      team: {
        create: jest.fn(),
        findMany: jest.fn(),
        findUnique: jest.fn(),
        update: jest.fn(),
      },
      teamMember: {
        create: jest.fn(),
        findUnique: jest.fn(),
        delete: jest.fn(),
      },
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TeamService,
        { provide: PrismaService, useValue: prisma },
      ],
    }).compile();

    service = module.get<TeamService>(TeamService);

    jest.clearAllMocks();
  });

  // ─── create ────────────────────────────────────────────────────────────

  describe('create', () => {
    it('creates a team and adds creator as first member', async () => {
      prisma.team.create.mockResolvedValue({ id: 'team-1', name: 'Team Alpha', createdBy: 'user-1' });
      prisma.teamMember.create.mockResolvedValue(mockMember);
      prisma.team.findUnique.mockResolvedValue(mockTeamDetail);

      const result = await service.create('Team Alpha', 'user-1');

      expect(prisma.team.create).toHaveBeenCalledWith({
        data: { name: 'Team Alpha', createdBy: 'user-1' },
      });
      expect(prisma.teamMember.create).toHaveBeenCalledWith({
        data: { teamId: 'team-1', userId: 'user-1' },
      });
      expect(result).toEqual(mockTeamDetail);
    });
  });

  // ─── findAll ───────────────────────────────────────────────────────────

  describe('findAll', () => {
    it('returns all active teams with member count and creator', async () => {
      prisma.team.findMany.mockResolvedValue([mockTeam, { ...mockTeam, id: 'team-2', name: 'Team Beta', _count: { members: 2 } }]);

      const result = await service.findAll();

      expect(result).toHaveLength(2);
      expect(result[0]).toHaveProperty('memberCount', 1);
      expect(result[0]).toHaveProperty('creator');
      expect(result[1]).toHaveProperty('memberCount', 2);
      expect(prisma.team.findMany).toHaveBeenCalledWith(
        expect.objectContaining({ where: { status: 'active' } }),
      );
    });

    it('returns empty array when no active teams', async () => {
      prisma.team.findMany.mockResolvedValue([]);

      const result = await service.findAll();

      expect(result).toEqual([]);
    });
  });

  // ─── findById ──────────────────────────────────────────────────────────

  describe('findById', () => {
    it('returns team detail with members and their profiles', async () => {
      prisma.team.findUnique.mockResolvedValue(mockTeamDetail);

      const result = await service.findById('team-1');

      expect(result).toEqual(mockTeamDetail);
      expect(result).toHaveProperty('members');
      expect(result.members).toHaveLength(1);
    });

    it('throws NotFoundException when team does not exist', async () => {
      prisma.team.findUnique.mockResolvedValue(null);

      await expect(service.findById('nonexistent')).rejects.toThrow(NotFoundException);
    });
  });

  // ─── addMember ─────────────────────────────────────────────────────────

  describe('addMember', () => {
    it('adds a member and returns with user info', async () => {
      prisma.team.findUnique.mockResolvedValue({ ...mockTeam, status: 'active', _count: { members: 1 } });
      prisma.teamMember.findUnique.mockResolvedValue(null);
      prisma.teamMember.create.mockResolvedValue(mockMember);

      const result = await service.addMember('team-1', 'user-2');

      expect(result).toEqual(mockMember);
      expect(prisma.teamMember.create).toHaveBeenCalledWith({
        data: { teamId: 'team-1', userId: 'user-2' },
        include: expect.any(Object),
      });
    });

    it('throws ConflictException when team is full (max 3 members)', async () => {
      prisma.team.findUnique.mockResolvedValue({ ...mockTeam, status: 'active', _count: { members: 3 } });
      prisma.teamMember.findUnique.mockResolvedValue(null);

      await expect(service.addMember('team-1', 'user-4')).rejects.toThrow(ConflictException);
      expect(prisma.teamMember.create).not.toHaveBeenCalled();
    });

    it('allows adding member when team has 2 members (under limit)', async () => {
      prisma.team.findUnique.mockResolvedValue({ ...mockTeam, status: 'active', _count: { members: 2 } });
      prisma.teamMember.findUnique.mockResolvedValue(null);
      prisma.teamMember.create.mockResolvedValue(mockMember);

      const result = await service.addMember('team-1', 'user-3');

      expect(result).toEqual(mockMember);
      expect(prisma.teamMember.create).toHaveBeenCalled();
    });

    it('throws ConflictException when user is already a member', async () => {
      prisma.team.findUnique.mockResolvedValue({ ...mockTeam, status: 'active', _count: { members: 1 } });
      prisma.teamMember.findUnique.mockResolvedValue(mockMember);

      await expect(service.addMember('team-1', 'user-2')).rejects.toThrow(ConflictException);
      expect(prisma.teamMember.create).not.toHaveBeenCalled();
    });

    it('throws ConflictException when team is archived', async () => {
      prisma.team.findUnique.mockResolvedValue({ ...mockTeam, status: 'archived', _count: { members: 1 } });
      prisma.teamMember.findUnique.mockResolvedValue(null);

      await expect(service.addMember('team-1', 'user-2')).rejects.toThrow(ConflictException);
    });

    it('throws NotFoundException when team does not exist', async () => {
      prisma.team.findUnique.mockResolvedValue(null);

      await expect(service.addMember('nonexistent', 'user-2')).rejects.toThrow(NotFoundException);
    });
  });

  // ─── removeMember ──────────────────────────────────────────────────────

  describe('removeMember', () => {
    it('removes a member and returns deleted:true', async () => {
      prisma.teamMember.findUnique.mockResolvedValue(mockMember);
      prisma.teamMember.delete.mockResolvedValue(mockMember);

      const result = await service.removeMember('team-1', 'user-2');

      expect(result).toEqual({ deleted: true });
      expect(prisma.teamMember.delete).toHaveBeenCalledWith({
        where: { id: 'member-1' },
      });
    });

    it('throws NotFoundException when user is not a member', async () => {
      prisma.teamMember.findUnique.mockResolvedValue(null);

      await expect(service.removeMember('team-1', 'ghost-user')).rejects.toThrow(NotFoundException);
      expect(prisma.teamMember.delete).not.toHaveBeenCalled();
    });
  });

  // ─── archive ───────────────────────────────────────────────────────────

  describe('archive', () => {
    it('archives an active team', async () => {
      prisma.team.findUnique.mockResolvedValue({ ...mockTeam, status: 'active' });
      const archivedTeam = { ...mockTeam, status: 'archived' };
      prisma.team.update.mockResolvedValue(archivedTeam);

      const result = await service.archive('team-1');

      expect(result).toEqual(archivedTeam);
      expect(prisma.team.update).toHaveBeenCalledWith({
        where: { id: 'team-1' },
        data: { status: 'archived' },
      });
    });

    it('returns team unchanged if already archived', async () => {
      prisma.team.findUnique.mockResolvedValue({ ...mockTeam, status: 'archived' });

      const result = await service.archive('team-1');

      expect(result).toEqual({ ...mockTeam, status: 'archived' });
      expect(prisma.team.update).not.toHaveBeenCalled();
    });

    it('throws NotFoundException when team does not exist', async () => {
      prisma.team.findUnique.mockResolvedValue(null);

      await expect(service.archive('nonexistent')).rejects.toThrow(NotFoundException);
    });
  });
});
