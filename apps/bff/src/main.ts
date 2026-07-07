import { NestFactory } from '@nestjs/core';
import { ConfigService } from '@nestjs/config';
import { AppModule } from './app.module';
import { WinstonModule } from 'nest-winston';
import * as winston from 'winston';
import { LoggingInterceptor } from './common/interceptors/logging.interceptor';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, {
    logger: WinstonModule.createLogger({
      transports: [
        new winston.transports.Console({
          format: winston.format.combine(
            winston.format.timestamp(),
            winston.format.ms(),
            winston.format.json(),
          ),
        }),
        new winston.transports.File({
          filename: 'logs/bff-error.log',
          level: 'error',
          format: winston.format.combine(
            winston.format.timestamp(),
            winston.format.json()
          )
        }),
        new winston.transports.File({
          filename: 'logs/bff-combined.log',
          format: winston.format.combine(
            winston.format.timestamp(),
            winston.format.json()
          )
        }),
      ],
    }),
  });
  
  app.setGlobalPrefix('api/v1');
  
  app.useGlobalInterceptors(new LoggingInterceptor());
  
  const configService = app.get(ConfigService);
    
  app.enableCors({
    origin: true, // 反射请求的 Origin，解决任何端口或 IP 带来的跨域问题
    credentials: true,
  });
  
  const port = configService.get<number>('BFF_PORT', 3000);
  await app.listen(port, '0.0.0.0');
}
bootstrap();
