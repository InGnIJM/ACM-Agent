import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { ProblemService } from './problem.service';

@ApiTags('Problems')
@Controller('api/problems')
export class ProblemController {
  constructor(private readonly problemService: ProblemService) {}

  @Get()
  @ApiOperation({ summary: 'List all problems' })
  async findAll(@Query() query: any) {
    return this.problemService.findAll(query);
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get problem by ID' })
  async findOne(@Param('id') id: string) {
    return this.problemService.findOne(id);
  }
}
