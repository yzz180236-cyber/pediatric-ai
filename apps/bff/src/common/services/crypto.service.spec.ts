import { Test, TestingModule } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import { CryptoService } from './crypto.service';

describe('CryptoService (SM4 国密升级测试)', () => {
  let service: CryptoService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        CryptoService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn().mockReturnValue(null),
            getOrThrow: jest.fn().mockReturnValue('super-secret-key-32-characters-long-key'),
          },
        },
      ],
    }).compile();

    service = module.get<CryptoService>(CryptoService);
    service.onModuleInit();
  });

  it('应该定义服务实例', () => {
    expect(service).toBeDefined();
  });

  it('应该能够成功使用 SM4 CBC 加密并解密还原明文', () => {
    const rawText = '这是一段极度敏感的儿科病历信息：患儿李某某确诊手足口病。';
    const encrypted = service.encrypt(rawText);
    
    // 密文应该以 "iv:ciphertext" 的形式存在
    expect(encrypted).toContain(':');
    const parts = encrypted.split(':');
    expect(parts.length).toBe(2);
    
    // 解密验证
    const decrypted = service.decrypt(encrypted);
    expect(decrypted).toBe(rawText);
  });

  it('使用随机 IV 机制，即使相同的明文多次加密，也应当产生截然不同的密文', () => {
    const text = '相同明文数据';
    const cipher1 = service.encrypt(text);
    const cipher2 = service.encrypt(text);
    
    expect(cipher1).not.toBe(cipher2);
  });

  it('输入格式错误的加密串时，解密应当抛出异常', () => {
    expect(() => {
      service.decrypt('invalid_format_without_colon');
    }).toThrow();
  });
});
