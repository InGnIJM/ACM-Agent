import { ApiProperty } from '@nestjs/swagger';

class RecommendCandidateDto {
  @ApiProperty({ description: 'User ID' })
  userId: string;

  @ApiProperty({ description: 'Username' })
  username: string;

  @ApiProperty({ description: 'Display nickname', required: false })
  nickname: string | null;

  @ApiProperty({ description: 'Overall profile score (0-1)' })
  overallScore: number;

  @ApiProperty({ description: 'Known skill tags', required: false })
  strengths: string[] | null;

  @ApiProperty({ description: 'Weak area tags', required: false })
  weaknesses: string[] | null;

  @ApiProperty({ description: 'Practice style label', required: false })
  style: string | null;

  @ApiProperty({ description: 'Pairwise compatibility with the current user' })
  compatibility: number;
}

class PairComplementDto {
  @ApiProperty({ description: 'Average skill complement across the trio' })
  skillComplement: number;

  @ApiProperty({ description: 'Average level proximity across the trio' })
  levelProximity: number;

  @ApiProperty({ description: 'Average style diversity across the trio' })
  styleDiversity: number;
}

export class RecommendItemDto {
  @ApiProperty({
    description: 'The three teammates (current user + two recommended)',
    type: [RecommendCandidateDto],
  })
  teammates: RecommendCandidateDto[];

  @ApiProperty({ description: 'Overall team score (0-1)' })
  teamScore: number;

  @ApiProperty({
    description: 'Pairwise compatibility: [user-t1, user-t2, t1-t2]',
  })
  pairScores: [number, number, number];

  @ApiProperty({ description: 'Complement breakdown for the trio' })
  complementDetails: PairComplementDto;

  @ApiProperty({ description: 'Ratio of distinct skill tags covered / 10' })
  skillCoverageRatio: number;
}

class UserInfoDto {
  @ApiProperty()
  userId: string;

  @ApiProperty()
  username: string;

  @ApiProperty({ required: false })
  nickname: string | null;

  @ApiProperty()
  overallScore: number;

  @ApiProperty({ required: false })
  strengths: string[] | null;

  @ApiProperty({ required: false })
  weaknesses: string[] | null;

  @ApiProperty({ required: false })
  style: string | null;
}

class CompatibilityBreakdownDto {
  @ApiProperty()
  skillComplement: number;

  @ApiProperty()
  levelProximity: number;

  @ApiProperty()
  styleDiversity: number;
}

export class CompatibilityResponseDto {
  @ApiProperty()
  user: UserInfoDto;

  @ApiProperty()
  target: UserInfoDto;

  @ApiProperty({ description: 'Overall compatibility score (0-1)' })
  compatibility: number;

  @ApiProperty()
  breakdown: CompatibilityBreakdownDto;
}
