import { Injectable } from '@nestjs/common';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, Strategy } from 'passport-jwt';
import { ConfigService } from '@nestjs/config';
import { AuthSource } from '@pediatric-ai/shared-types';
import { UserRole } from '../../database/entities/user.entity';

interface JwtPayload {
  sub: string;
  openid: string;
  authSource: AuthSource;
  role: UserRole;
  iat: number;
  exp: number;
}

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
  constructor(config: ConfigService) {
    super({
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      secretOrKey: config.getOrThrow('JWT_PUBLIC_KEY').replace(/\\n/g, '\n'),
      algorithms: ['RS256'],
    });
  }

  validate(payload: JwtPayload): { userId: string; openid: string; authSource: AuthSource; role: UserRole } {
    return { userId: payload.sub, openid: payload.openid, authSource: payload.authSource, role: payload.role };
  }
}
