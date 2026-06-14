import { Injectable } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';

@Injectable()
export class OptionalAuthGuard extends AuthGuard('jwt') {
  handleRequest<TUser = any>(_err: any, user: TUser): TUser {
    if (!user) {
      return null as any;
    }
    return user;
  }
}
