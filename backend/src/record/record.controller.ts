import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { RecordService } from './record.service';

@ApiTags('Records')
@Controller('api/records')
export class RecordController {
  constructor(private readonly recordService: RecordService) {}

  @Get()
  @ApiOperation({ summary: 'List all submission records' })
  async findAll(@Query() query: any) {
    return this.recordService.findAll(query);
  }

  @Get(':id')
  @ApiOperation({ summary: 'Get record by ID' })
  async findOne(@Param('id') id: string) {
    return this.recordService.findOne(id);
  }
}
