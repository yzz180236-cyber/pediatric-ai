import { Injectable, UnauthorizedException, Logger } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { AuthSource } from '@pediatric-ai/shared-types';
import { UserRole } from '../database/entities/user.entity';

interface WxSession {
  openid: string;
  session_key: string;
  unionid?: string;
  errcode?: number;
  errmsg?: string;
}

import { DataSource } from 'typeorm';

interface LoginInput {
  code?: string;
  username?: string;
  password?: string;
}

@Injectable()
export class AuthService {
  private readonly logger = new Logger(AuthService.name);

  constructor(
    private readonly jwtService: JwtService,
    private readonly httpService: HttpService,
    private readonly config: ConfigService,
    private readonly dataSource: DataSource,
  ) {}

  async login(input: LoginInput): Promise<{ accessToken: string; expiresIn: number; userId: string; authSource: AuthSource; role: UserRole }> {
    const username = input.username?.trim();
    const password = input.password?.trim();

    if (username || password) {
      return this.devLogin(username, password);
    }

    if (!input.code) {
      throw new UnauthorizedException('缺少登录参数');
    }

    return this.wxLogin(input.code);
  }

  async wxLogin(code: string): Promise<{ accessToken: string; expiresIn: number; userId: string; authSource: AuthSource; role: UserRole }> {
    let openid: string;
    let userId: string;
    let role: UserRole = 'user';

    let wxSession: WxSession;
    try {
      wxSession = await this.getWxSession(code);
    } catch (error) {
      this.logger.warn('请求微信 code2session 失败');
      throw new UnauthorizedException('微信登录失败');
    }
    if (wxSession.errcode || !wxSession.openid) {
      this.logger.warn(`微信 code2session 失败: ${wxSession.errmsg || 'unknown error'}`);
      throw new UnauthorizedException('微信登录失败');
    }
    openid = wxSession.openid;

    try {
      const result = await this.dataSource.query(
        `INSERT INTO users (openid, auth_source, unionid, role, last_login_at)
         VALUES ($1, $2, $3, $4, NOW())
         ON CONFLICT (openid)
         DO UPDATE SET auth_source = EXCLUDED.auth_source, unionid = EXCLUDED.unionid, last_login_at = NOW()
         RETURNING id, role`,
        [openid, 'wechat', wxSession.unionid ?? null, role]
      );
      userId = result[0].id as string;
      role = (result[0].role as UserRole) || 'user';
    } catch (e) {
      this.logger.error('插入测试用户失败', e);
      throw new UnauthorizedException('用户登录失败');
    }

    const payload = { sub: userId, openid, authSource: 'wechat' as AuthSource, role };
    const accessToken = this.jwtService.sign(payload);

    this.logger.log(`成功颁发真实 JWT (userId: ${userId}, openid: ${openid.slice(0, 15)}...)`);

    return { accessToken, expiresIn: 7200, userId, authSource: 'wechat', role };
  }

  private async devLogin(
    username?: string,
    password?: string,
  ): Promise<{ accessToken: string; expiresIn: number; userId: string; authSource: AuthSource; role: UserRole }> {
    const runtimeEnv =
      this.config.get<string>('NODE_ENV') ??
      process.env.NODE_ENV ??
      'development';

    if (runtimeEnv === 'production') {
      throw new UnauthorizedException('开发登录仅允许在开发环境使用');
    }

    const devAccounts: Record<string, { password: string; role: UserRole }> = {
      boluo123: { password: 'admin123', role: 'user' },
      doctor001: { password: 'admin123', role: 'doctor' },
    };

    if (!username || !devAccounts[username] || password !== devAccounts[username].password) {
      throw new UnauthorizedException('账号或密码错误');
    }

    const role = devAccounts[username].role;
    const openid = `dev-${username}`;
    let userId: string;

    try {
      const result = await this.dataSource.query(
        `INSERT INTO users (openid, auth_source, dev_username, role, last_login_at)
         VALUES ($1, $2, $3, $4, NOW())
         ON CONFLICT (openid)
         DO UPDATE SET auth_source = EXCLUDED.auth_source, dev_username = EXCLUDED.dev_username, role = EXCLUDED.role, last_login_at = NOW()
         RETURNING id, role`,
        [openid, 'dev', username, role]
      );
      userId = result[0].id as string;
      const persistedRole = (result[0].role as UserRole) || role;
      const payload = { sub: userId, openid, authSource: 'dev' as AuthSource, role: persistedRole };
      const accessToken = this.jwtService.sign(payload);
      this.logger.log(`开发登录成功 (username: ${username}, userId: ${userId}, role: ${persistedRole})`);
      return { accessToken, expiresIn: 7200, userId, authSource: 'dev', role: persistedRole };
    } catch (error) {
      this.logger.error('开发用户登录失败', error);
      throw new UnauthorizedException('开发登录失败');
    }
  }

  private async getWxSession(code: string): Promise<WxSession> {
    const url = 'https://api.weixin.qq.com/sns/jscode2session';
    const params = {
      appid: this.config.getOrThrow('WX_APPID'),
      secret: this.config.getOrThrow('WX_SECRET'),
      js_code: code,
      grant_type: 'authorization_code',
    };

    const response = await firstValueFrom(
      this.httpService.get<WxSession>(url, { params })
    );

    return response.data;
  }
}
