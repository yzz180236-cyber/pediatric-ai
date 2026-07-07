import { Controller, Post, Body, HttpCode, HttpStatus } from '@nestjs/common';
import { IsOptional, IsString, IsNotEmpty } from 'class-validator';
import { AuthService } from './auth.service';
import { AuthSource } from '@pediatric-ai/shared-types';
import { UserRole } from '../database/entities/user.entity';

export class WxLoginDto {
  @IsOptional()
  @IsString()
  code?: string;

  @IsOptional()
  @IsString()
  username?: string;

  @IsOptional()
  @IsString()
  password?: string;
}

export class AuthResponseDto {
  accessToken: string;
  expiresIn: number;
  userId: string;
  authSource: AuthSource;
  role: UserRole;
}

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  @Post('login')
  @HttpCode(HttpStatus.OK)
  async wxLogin(@Body() dto: WxLoginDto): Promise<AuthResponseDto> {
    return this.authService.login(dto);
  }
}
