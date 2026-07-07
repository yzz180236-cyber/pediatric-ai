import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
  Logger,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { v4 as uuidv4 } from 'uuid';

@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  private readonly logger = new Logger('HTTP');

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const ctx = context.switchToHttp();
    const request = ctx.getRequest();
    const response = ctx.getResponse();

    const { method, originalUrl, ip } = request;
    const userAgent = request.get('user-agent') || '';
    
    // 生成或提取 traceId
    const traceId = request.headers['x-trace-id'] || uuidv4();
    request.headers['x-trace-id'] = traceId;

    // 尝试提取用户 ID
    const userId = request.user?.id || 'anonymous';

    const now = Date.now();

    return next.handle().pipe(
      tap(() => {
        const { statusCode } = response;
        const durationMs = Date.now() - now;

        const logFormat = {
          traceId,
          userId,
          method,
          url: originalUrl,
          status: statusCode,
          duration_ms: durationMs,
          ip,
          userAgent,
        };

        if (statusCode >= 500) {
          this.logger.error(JSON.stringify(logFormat));
        } else if (statusCode >= 400) {
          this.logger.warn(JSON.stringify(logFormat));
        } else {
          this.logger.log(JSON.stringify(logFormat));
        }
      }),
    );
  }
}
