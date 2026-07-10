import { CanActivate, ExecutionContext, HttpException, HttpStatus, Injectable } from '@nestjs/common';
import { InjectRedis } from '@nestjs-modules/ioredis';
import Redis from 'ioredis';
import { sm3 } from 'sm-crypto';

@Injectable()
export class AntiReplayGuard implements CanActivate {
  // 时效窗口时间定义为 60 秒 (60000 毫秒)
  private readonly WINDOW_MILLIS = 60000;

  constructor(@InjectRedis() private readonly redis: Redis) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest();
    const path = request.path;

    // 放行无需签名的公开端点（如监控指标、健康度、Swagger 等）
    if (
      path === '/metrics' || 
      path === '/health' || 
      path === '/' || 
      path.startsWith('/swagger')
    ) {
      return true;
    }

    const headers = request.headers;
    const signature = headers['x-signature'];
    const timestampStr = headers['x-timestamp'];
    const nonce = headers['x-nonce'];

    // 1. 基本参数完整性校验
    if (!signature || !timestampStr || !nonce) {
      throw new HttpException(
        '【签名熔断】缺少必要的安全请求头 x-signature、x-timestamp 或 x-nonce',
        HttpStatus.BAD_REQUEST
      );
    }

    const timestamp = parseInt(timestampStr as string, 10);
    if (isNaN(timestamp)) {
      throw new HttpException(
        '【签名熔断】时间戳 x-timestamp 格式非法',
        HttpStatus.BAD_REQUEST
      );
    }

    // 2. 时间戳时效窗口校验（抗时间拉开的二次重放）
    const now = Date.now();
    if (Math.abs(now - timestamp) > this.WINDOW_MILLIS) {
      throw new HttpException(
        '【签名熔断】请求已超出 60s 时效限制，疑似重放请求',
        HttpStatus.FORBIDDEN
      );
    }

    // 3. Nonce 防重放校验（基于 Redis 实现防篡改和去重）
    const redisKey = `anti_replay_nonce:${nonce}`;
    // 使用 setnx (set string key value EX seconds NX) 来保证原子性唯一消费
    const acquired = await this.redis.set(redisKey, '1', 'PX', this.WINDOW_MILLIS, 'NX');
    if (!acquired) {
      throw new HttpException(
        '【签名熔断】检测到重复的 Nonce 标识，请求已被拒绝',
        HttpStatus.FORBIDDEN
      );
    }

    // 4. 双向 SM3 签名防篡改校验
    let bodyStr = '';
    if (request.body && Object.keys(request.body).length > 0) {
      // 保持 stringify 键的顺序一致性以保证生成算法一致性
      bodyStr = JSON.stringify(request.body);
    }

    // 拼接消息报文：timestamp + nonce + bodyStr
    const rawData = `${timestampStr}${nonce}${bodyStr}`;
    
    // 使用国密 SM3 计算摘要签名
    const expectedSignature = sm3(rawData);

    if (signature !== expectedSignature) {
      throw new HttpException(
        '【签名熔断】双向国密 SM3 签名校验失败，数据可能已遭篡改',
        HttpStatus.FORBIDDEN
      );
    }

    return true;
  }
}
