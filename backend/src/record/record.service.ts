import { Injectable } from '@nestjs/common';

@Injectable()
export class RecordService {
  async findAll(_query: any) {
    return { data: [], total: 0, message: 'Record module stub' };
  }

  async findOne(id: string) {
    return { data: null, message: `Record ${id} stub` };
  }
}
