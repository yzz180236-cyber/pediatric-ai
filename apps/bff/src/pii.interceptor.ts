import { CallHandler, ExecutionContext, HttpException, HttpStatus, Injectable, NestInterceptor } from '@nestjs/common';
import { Observable } from 'rxjs';

@Injectable()
export class PiiInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const body = request.body;

    if (body && typeof body.message === 'string') {
      const message = body.message;
      // 匹配 11位大陆手机号
      const phoneRegex = /1[3-9]\d{9}/;
      // 匹配 18位二代身份证号
      const idCardRegex = /[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]/;

      if (phoneRegex.test(message) || idCardRegex.test(message)) {
        throw new HttpException(
          '【合规熔断】请求体中检测到高危 PII 数据（手机号或身份证），为了保护患者隐私，已强制阻断。',
          HttpStatus.FORBIDDEN
        );
      }

      const dangerousRegex = /偏方|安宫牛黄丸|阿莫西林|头孢|土方|神药|包治百病|偏门/
      if (dangerousRegex.test(message)) {
        throw new HttpException(
          '【合规熔断】检测到请求中包含高危医疗词汇或处方药建议，违背平台安全底线，已强制阻断。',
          HttpStatus.FORBIDDEN
        );
      }

      const emergencyRegex = /惊厥|抽搐|窒息|昏迷|大量出血|叫不醒|口吐白沫/
      if (emergencyRegex.test(message)) {
        throw new HttpException(
          '【紧急熔断】检测到高危症状描述，请立即拨打 120 急救电话或前往最近的急诊科就医，切勿等待线上问诊！',
          HttpStatus.FORBIDDEN
        );
      }
    }

    // 通过检验，继续流转
    return next.handle();
  }
}
