import { IsArray, ArrayMinSize } from 'class-validator';

export class DeleteProblemsDto {
  @IsArray()
  @ArrayMinSize(1)
  ids: string[];
}
