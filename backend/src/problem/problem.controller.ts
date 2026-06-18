import { Controller, Get, Post, Delete, Param, Query, Body } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { ProblemService } from './problem.service';

@ApiTags('Problems')
@Controller('api/problems')
export class ProblemController {
  constructor(private readonly problemService: ProblemService) {}

  @Get()
  @ApiOperation({ summary: 'List problems with optional filters (search, platform, difficulty, tags)' })
  async findAll(@Query() query: any) {
    return this.problemService.findAll(query);
  }

  @Get('search')
  @ApiOperation({ summary: 'Full-text search problems by title' })
  async search(@Query('q') q: string) {
    return this.problemService.searchProblems(q || '');
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get problem by ID (includes solutions)' })
  async findOne(@Param('id') id: string) {
    return this.problemService.findOne(id);
  }

  @Get(':id/similar')
  @ApiOperation({ summary: 'Get similar problems by tag overlap' })
  async getSimilar(@Param('id') id: string) {
    return this.problemService.getSimilarProblems(id);
  }

  @Delete(':id')
  @ApiOperation({ summary: 'Soft-delete a problem' })
  async deleteOne(@Param('id') id: string) {
    return this.problemService.deleteOne(id);
  }

  @Post('search/vector')
  @ApiOperation({ summary: 'Semantic vector search (ANN via pgvector)' })
  async searchByVector(@Body() dto: any) {
    return this.problemService.searchByVector(dto);
  }

  @Post('batch-delete')
  @ApiOperation({ summary: 'Soft-delete multiple problems' })
  async batchDelete(@Body() body: { ids: string[] }) {
    return this.problemService.deleteMany(body.ids || []);
  }
}
