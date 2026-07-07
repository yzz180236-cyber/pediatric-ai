import { Injectable, Logger } from '@nestjs/common';
import { InjectRedis } from '@nestjs-modules/ioredis';
import Redis from 'ioredis';
import { randomUUID } from 'crypto';

@Injectable()
export class SessionService {
  private readonly logger = new Logger(SessionService.name);
  private readonly SESSION_TIMEOUT_SECONDS = 3600; // 会话超时时间，默认 1 小时无交流则新开一轮

  constructor(@InjectRedis() private readonly redis: Redis) {}

  /**
   * 获取用户当前活跃的 Session ID。如果已超时或不存在，则创建一个新的并返回。
   * 同时自动刷新活跃时间。
   */
  async getActiveSessionId(userId: string): Promise<string> {
    const redisKey = `user_active_session:${userId}`;
    let sessionId = await this.redis.get(redisKey);

    if (!sessionId) {
      sessionId = randomUUID();
      this.logger.log(`[SessionService] User ${userId} created new session: ${sessionId}`);
    }

    // 每次交互重置过期时间
    await this.redis.set(redisKey, sessionId, 'EX', this.SESSION_TIMEOUT_SECONDS);
    return sessionId;
  }

  /**
   * 强制结束当前会话
   */
  async clearSession(userId: string): Promise<void> {
    const redisKey = `user_active_session:${userId}`;
    await this.redis.del(redisKey);
    this.logger.log(`[SessionService] User ${userId} session cleared`);
  }
}
