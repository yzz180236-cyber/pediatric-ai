import { Injectable, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as crypto from 'crypto';
import { sm4 } from 'sm-crypto';

@Injectable()
export class CryptoService implements OnModuleInit {
  private keyHex: string;

  constructor(private configService: ConfigService) {}

  onModuleInit() {
    // 优先从 SM4_SECRET_KEY 读取，如果未配置则降级沿用 AES_SECRET_KEY
    const secret = this.configService.get<string>('SM4_SECRET_KEY') || this.configService.getOrThrow<string>('AES_SECRET_KEY');
    
    // 国密 SM4 密钥长度为 128 位 (16 字节)
    // 使用 scryptSync 生成 16 字节 Key 并转换为 32 位十六进制字符串
    const keyBuffer = crypto.scryptSync(secret, 'salt', 16);
    this.keyHex = keyBuffer.toString('hex');
  }

  /**
   * 使用国密 SM4 CBC 模式对敏感信息进行加密
   * 返回格式 ivHex:ciphertextHex 保持与原本的 AES 设计一致，以便无缝升级
   */
  encrypt(text: string): string {
    // 生成 16 字节的随机 IV 并转换为 32 位十六进制字符串
    const ivHex = crypto.randomBytes(16).toString('hex');
    
    const encrypted = sm4.encrypt(text, this.keyHex, {
      mode: 'cbc',
      iv: ivHex,
    });
    
    return `${ivHex}:${encrypted}`;
  }

  /**
   * 使用国密 SM4 CBC 模式对加密信息进行解密
   */
  decrypt(encryptedData: string): string {
    const parts = encryptedData.split(':');
    if (parts.length !== 2) throw new Error('Invalid encrypted data format');
    
    const ivHex = parts[0];
    const encryptedText = parts[1];
    
    const decrypted = sm4.decrypt(encryptedText, this.keyHex, {
      mode: 'cbc',
      iv: ivHex,
    });
    
    return decrypted;
  }
}
