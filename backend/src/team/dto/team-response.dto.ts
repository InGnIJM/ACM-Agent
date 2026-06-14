import { ApiProperty } from '@nestjs/swagger';
import { TeamStatus } from '@prisma/client';

class TeamMemberUserDto {
  @ApiProperty()
  id: string;

  @ApiProperty()
  username: string;

  @ApiProperty({ required: false })
  nickname: string | null;

  @ApiProperty({ required: false })
  studentId: string | null;

  @ApiProperty({ required: false })
  department: string | null;

  @ApiProperty({ required: false })
  major: string | null;

  @ApiProperty({ required: false })
  profile: unknown;
}

class TeamMemberDto {
  @ApiProperty()
  id: string;

  @ApiProperty()
  teamId: string;

  @ApiProperty()
  userId: string;

  @ApiProperty()
  joinedAt: Date;

  @ApiProperty({ type: TeamMemberUserDto })
  user: TeamMemberUserDto;
}

class TeamCreatorDto {
  @ApiProperty()
  id: string;

  @ApiProperty()
  username: string;

  @ApiProperty({ required: false })
  nickname: string | null;
}

export class TeamResponseDto {
  @ApiProperty()
  id: string;

  @ApiProperty()
  name: string;

  @ApiProperty({ enum: TeamStatus })
  status: TeamStatus;

  @ApiProperty()
  createdBy: string;

  @ApiProperty({ type: TeamCreatorDto })
  creator: TeamCreatorDto;

  @ApiProperty({ type: [TeamMemberDto] })
  members: TeamMemberDto[];

  @ApiProperty()
  createdAt: Date;

  @ApiProperty()
  updatedAt: Date;
}

export class TeamListItemDto {
  @ApiProperty()
  id: string;

  @ApiProperty()
  name: string;

  @ApiProperty({ enum: TeamStatus })
  status: TeamStatus;

  @ApiProperty()
  createdBy: string;

  @ApiProperty({ type: TeamCreatorDto })
  creator: TeamCreatorDto;

  @ApiProperty()
  memberCount: number;

  @ApiProperty()
  createdAt: Date;

  @ApiProperty()
  updatedAt: Date;
}
