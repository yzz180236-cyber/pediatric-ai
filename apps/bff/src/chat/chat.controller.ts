import { Controller, Post, Body, UseGuards, Get, Res, Req, Param, Delete, UnauthorizedException, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import type { Response } from 'express';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { ChatService } from './chat.service';

interface UploadedBinaryFile {
  buffer: Buffer;
  mimetype: string;
  originalname: string;
}

@Controller('chat')
@UseGuards(JwtAuthGuard)
export class ChatController {
  constructor(private readonly chatService: ChatService) {}

  private getUserId(req: Request): string {
    const userId = (req as any).user?.userId;
    if (!userId) {
      throw new UnauthorizedException('用户未登录');
    }
    return userId;
  }

  @Post('sessions')
  async createSession(@Req() req: Request) {
    const userId = this.getUserId(req);
    return this.chatService.createSession(userId);
  }

  @Get('sessions')
  async getSessions(@Req() req: Request) {
    const userId = this.getUserId(req);
    return this.chatService.getSessions(userId);
  }

  @Get('sessions/:id/messages')
  async getSessionMessages(@Param('id') sessionId: string, @Req() req: Request) {
    const userId = this.getUserId(req);
    const messages = await this.chatService.getSessionMessages(sessionId, userId);
    return messages.map(msg => ({
      ...msg,
      role: msg.sender,
      sender: undefined,
    }));
  }

  @Delete('sessions/:id')
  async deleteSession(@Param('id') sessionId: string, @Req() req: Request) {
    const userId = this.getUserId(req);
    return await this.chatService.deleteSession(sessionId, userId);
  }

  @Post('stream')
  async sendMessageStream(
    @Body('sessionId') sessionId: string,
    @Body('message') message: string,
    @Body('image') image: string | null,
    @Body('imageFileId') imageFileId: string | null,
    @Body('history') history: Record<string, unknown>[],
    @Req() req: Request,
    @Res() res: Response
  ) {
    if (!sessionId) {
      res.status(400).send('sessionId is required');
      return;
    }
    // 从 JWT 中提取 userId，传入 service 以读取患儿档案
    const userId = this.getUserId(req);
    const stream = await this.chatService.askAiStream(
      userId,
      sessionId,
      message,
      image ?? null,
      imageFileId ?? null,
      history ?? []
    );
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    stream.pipe(res);
  }

  @Post('files')
  @UseInterceptors(FileInterceptor('file'))
  async uploadFile(
    @UploadedFile() file: UploadedBinaryFile,
    @Req() req: Request,
  ) {
    const userId = this.getUserId(req);
    return this.chatService.uploadImage(userId, file);
  }

  @Get('files/:id')
  async getFile(
    @Param('id') fileId: string,
    @Req() req: Request,
    @Res() res: Response,
  ) {
    const userId = this.getUserId(req);
    const file = await this.chatService.getImageForUser(userId, fileId);
    res.setHeader('Content-Type', file.mimeType);
    res.send(file.buffer);
  }
}
