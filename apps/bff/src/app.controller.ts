import { Controller, Post, Body, HttpException, HttpStatus, UseInterceptors } from '@nestjs/common';
import { PiiInterceptor } from './pii.interceptor';

@Controller('api/ai')
export class AppController {
  
  @Post('chat')
  @UseInterceptors(PiiInterceptor) // 启用 PII 安全拦截器
  async handleChat(@Body() body: { message: string }) {
    // 1. 将患者真实身份替换为 Hash UUID (安全隔离底线)
    const safeHashId = 'hash-uuid-abc-123';

    try {
      // 2. 代理透传至 Python AI Engine 8000端口
      const aiResponse = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: body.message }),
      });
      
      const aiData = await aiResponse.json();
      return {
        code: 200,
        data: aiData,
        _traceId: safeHashId
      };
    } catch (err) {
      throw new HttpException('AI 引擎连接超时或未启动', HttpStatus.GATEWAY_TIMEOUT);
    }
  }
}
