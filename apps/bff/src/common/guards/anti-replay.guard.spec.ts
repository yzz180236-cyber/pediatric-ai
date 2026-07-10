import { Test, TestingModule } from '@nestjs/testing';
import { HttpException, HttpStatus } from '@nestjs/common';
import { getRedisConnectionToken } from '@nestjs-modules/ioredis';
import Redis from 'ioredis';
import { sm3 } from 'sm-crypto';
import { AntiReplayGuard } from './anti-replay.guard';

describe('AntiReplayGuard (防重放与签名篡改守卫测试)', () => {
  let guard: AntiReplayGuard;
  let mockRedis: Record<string, jest.Mock>;

  beforeEach(async () => {
    mockRedis = {
      get: jest.fn(),
      set: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AntiReplayGuard,
        {
          provide: getRedisConnectionToken(),
          useValue: mockRedis,
        },
      ],
    }).compile();

    guard = module.get<AntiReplayGuard>(AntiReplayGuard);
  });

  const createMockContext = (headers: Record<string, string>, body: any, path = '/chat/ask'): any => {
    return {
      switchToHttp: () => ({
        getRequest: () => ({
          path,
          headers,
          body,
        }),
      }),
    };
  };

  it('应该定义守卫实例', () => {
    expect(guard).toBeDefined();
  });

  it('应该放行指标健康状态等公开 API', async () => {
    const context = createMockContext({}, {}, '/metrics');
    const result = await guard.canActivate(context);
    expect(result).toBe(true);
  });

  it('缺少必要参数应抛出 400 Bad Request', async () => {
    const context = createMockContext({
      'x-timestamp': '1719999999000',
    }, {});
    
    await expect(guard.canActivate(context)).rejects.toThrow(
      new HttpException('【签名熔断】缺少必要的安全请求头 x-signature、x-timestamp 或 x-nonce', HttpStatus.BAD_REQUEST)
    );
  });

  it('时间戳差值超过 60s 应当判定为过期并抛出 403 Forbidden', async () => {
    const expiredTimestamp = Date.now() - 70000; // 过期 70 秒
    const context = createMockContext({
      'x-signature': 'sig',
      'x-timestamp': expiredTimestamp.toString(),
      'x-nonce': 'nonce-123',
    }, {});

    await expect(guard.canActivate(context)).rejects.toThrow(
      new HttpException('【签名熔断】请求已超出 60s 时效限制，疑似重放请求', HttpStatus.FORBIDDEN)
    );
  });

  it('二次使用相同的 Nonce 应当触发 Redis 占用阻断并抛出 403 Forbidden', async () => {
    const nowStr = Date.now().toString();
    const context = createMockContext({
      'x-signature': 'sig',
      'x-timestamp': nowStr,
      'x-nonce': 'nonce-duplicate',
    }, {});

    // 模拟 Redis set 返回 null 代表该 Nonce 已经被其他人提前消费过
    mockRedis.set.mockResolvedValue(null);

    await expect(guard.canActivate(context)).rejects.toThrow(
      new HttpException('【签名熔断】检测到重复的 Nonce 标识，请求已被拒绝', HttpStatus.FORBIDDEN)
    );
  });

  it('签名一致且数据未被修改的请求应顺利返回 true 通过', async () => {
    const nowStr = Date.now().toString();
    const nonce = 'nonce-success';
    const body = { message: '正常问诊消息' };
    
    // 计算期望签名：timestamp + nonce + bodyStr
    const rawData = `${nowStr}${nonce}${JSON.stringify(body)}`;
    const signature = sm3(rawData);

    const context = createMockContext({
      'x-signature': signature,
      'x-timestamp': nowStr,
      'x-nonce': nonce,
    }, body);

    // 模拟 Redis set 返回 'OK' 代表锁定该 Nonce 成功
    mockRedis.set.mockResolvedValue('OK');

    const result = await guard.canActivate(context);
    expect(result).toBe(true);
  });

  it('传输 Body 发生变化导致签名不符应当抛出 403 Forbidden 提示篡改', async () => {
    const nowStr = Date.now().toString();
    const nonce = 'nonce-tamper';
    const originalBody = { message: '正常问诊' };
    
    // 原签名
    const originalRaw = `${nowStr}${nonce}${JSON.stringify(originalBody)}`;
    const originalSignature = sm3(originalRaw);

    // 篡改后的 body 交互
    const tamperedBody = { message: '被篡改的恶意问诊' };
    const context = createMockContext({
      'x-signature': originalSignature, // 传递原签名，但 body 变了
      'x-timestamp': nowStr,
      'x-nonce': nonce,
    }, tamperedBody);

    mockRedis.set.mockResolvedValue('OK');

    await expect(guard.canActivate(context)).rejects.toThrow(
      new HttpException('【签名熔断】双向国密 SM3 签名校验失败，数据可能已遭篡改', HttpStatus.FORBIDDEN)
    );
  });
});
