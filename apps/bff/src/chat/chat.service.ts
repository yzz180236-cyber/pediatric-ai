import { Injectable, InternalServerErrorException, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';
import { CryptoService } from '../common/services/crypto.service';
import { PatientService } from '../patient/patient.service';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ChatSessionEntity } from '../database/entities/chat-session.entity';
import { ChatMessageEntity } from '../database/entities/chat-message.entity';
import { UploadedImageEntity } from '../database/entities/uploaded-image.entity';

interface UploadedBinaryFile {
  buffer: Buffer;
  mimetype: string;
  originalname: string;
}

@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);
  private readonly aiEngineUrl: string;
  private readonly aiEngineInternalToken: string;

  constructor(
    private readonly httpService: HttpService,
    private readonly cryptoService: CryptoService,
    private readonly configService: ConfigService,
    private readonly patientService: PatientService,
    @InjectRepository(ChatSessionEntity)
    private readonly sessionRepository: Repository<ChatSessionEntity>,
    @InjectRepository(ChatMessageEntity)
    private readonly messageRepository: Repository<ChatMessageEntity>,
    @InjectRepository(UploadedImageEntity)
    private readonly uploadedImageRepository: Repository<UploadedImageEntity>,
  ) {
    this.aiEngineUrl = this.configService.get<string>('AI_ENGINE_URL', 'http://localhost:8000');
    this.aiEngineInternalToken = this.configService.get<string>('AI_ENGINE_INTERNAL_TOKEN', 'dev-internal-token');
  }

  async createSession(userId: string): Promise<ChatSessionEntity> {
    try {
      const session = this.sessionRepository.create({ userId, lastActiveAt: new Date() });
      return await this.sessionRepository.save(session);
    } catch (error: unknown) {
      const err = error as Error;
      this.logger.error('创建会话失败: ' + err.message);
      throw new InternalServerErrorException(err.message);
    }
  }

  async getSessions(userId: string): Promise<ChatSessionEntity[]> {
    return await this.sessionRepository.find({
      where: { userId },
      order: { lastActiveAt: 'DESC' },
    });
  }

  async getSessionMessages(sessionId: string, userId: string): Promise<ChatMessageEntity[]> {
    const session = await this.sessionRepository.findOne({ where: { id: sessionId, userId } });
    if (!session) throw new InternalServerErrorException('Session not found or forbidden');
    return await this.messageRepository.find({
      where: { sessionId },
      order: { createdAt: 'ASC' },
    });
  }

  async deleteSession(sessionId: string, userId: string): Promise<void> {
    const session = await this.sessionRepository.findOne({ where: { id: sessionId, userId } });
    if (!session) throw new InternalServerErrorException('Session not found or forbidden');
    await this.sessionRepository.delete(sessionId);
  }

  async applySessionAction(
    sessionId: string,
    userId: string,
    action: 'mark_followup' | 'request_doctor_review',
  ): Promise<{ sessionId: string; status: 'active' | 'followup' | 'closed'; doctorNote: string }> {
    const session = await this.sessionRepository.findOne({ where: { id: sessionId, userId } });
    if (!session) {
      throw new InternalServerErrorException('Session not found or forbidden');
    }

    const latestAiMessage = await this.messageRepository.findOne({
      where: { sessionId, sender: 'ai' },
      order: { createdAt: 'DESC' },
    });
    const assessment = latestAiMessage?.assessment as Record<string, unknown> | null;
    const triageReason = typeof assessment?.triageReason === 'string' ? assessment.triageReason : '';
    const summaryText = typeof assessment?.summaryText === 'string' ? assessment.summaryText : '';

    session.status = 'followup';

    if (action === 'request_doctor_review') {
      const reviewNote = [
        '[家长请求医生复核]',
        summaryText || '',
        triageReason ? `分诊原因：${triageReason}` : '',
      ]
        .filter(Boolean)
        .join('\n');
      session.doctorNote = reviewNote;
    } else if (!session.doctorNote) {
      session.doctorNote = '[家长标记为需随访]';
    }

    const saved = await this.sessionRepository.save(session);
    return {
      sessionId: saved.id,
      status: saved.status,
      doctorNote: saved.doctorNote ?? '',
    };
  }

  async askAiStream(
    userId: string,
    sessionId: string,
    message: string,
    image: string | null = null,
    imageFileId: string | null = null,
    history: Record<string, unknown>[] = []
  ): Promise<NodeJS.ReadableStream> {
    try {
      const resolvedImage = imageFileId
        ? await this.resolveInternalImageRef(userId, imageFileId)
        : image;
      const encryptedMsg = this.cryptoService.encrypt(message);
      this.logger.log(`【流式请求】Session: ${sessionId}, 密文: ${encryptedMsg}, 带图片: ${!!resolvedImage}`);

      // 落库用户消息
      await this.messageRepository.save({
        sessionId,
        sender: 'user',
        content: message,
        imageUrl: image,
      });

      // 【P0.1 核心】读取患儿档案摘要，注入给 AI Engine
      const patientProfile = await this.patientService.getProfileSummary(userId);
      const patientContext = await this.patientService.getClinicalContext(userId);
      if (patientProfile) {
        this.logger.log(`已为用户 ${userId.slice(0, 8)} 注入患儿档案摘要 (${patientProfile.length} 字符)`);
      }

      const startTime = Date.now();
      const response = await firstValueFrom(
        this.httpService.post(
          `${this.aiEngineUrl}/api/chat/stream`,
          { sessionId, message, image: resolvedImage, history, patientProfile, patientContext },
          { responseType: 'stream' }
        )
      );

      // 拦截底层流，用于落库和档案更新
      let buffer = '';
      let text = '';
      const thoughts: string[] = [];
      let citations: Record<string, unknown>[] = [];
      let finalSlots: Record<string, string> = {};
      let ocrResult: Record<string, unknown> | null = null;
      let assessment: Record<string, unknown> | null = null;

      response.data.on('data', (chunk: Buffer) => {
        buffer += chunk.toString('utf-8');
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const part of parts) {
          const lines = part.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6);
              if (dataStr === '[DONE]') continue;
              try {
                const data = JSON.parse(dataStr) as Record<string, unknown>;
                if (data.chunk) text += data.chunk as string;
                if (data.thought && !thoughts.includes(data.thought as string)) {
                  thoughts.push(data.thought as string);
                }
                if (data.citations) citations = data.citations as Record<string, unknown>[];
                if (data.slots) finalSlots = data.slots as Record<string, string>;
                if (data.ocr_result) ocrResult = data.ocr_result as Record<string, unknown>;
                if (data.assessment) assessment = data.assessment as Record<string, unknown>;
              } catch {
                // 忽略解析失败的片段
              }
            }
          }
        }
      });

      response.data.on('end', async () => {
        // 更新会话最后活跃时间
        await this.sessionRepository.update(sessionId, { lastActiveAt: new Date() });

        // 落库 AI 的完整回复
        await this.messageRepository.save({
          sessionId,
          sender: 'ai',
          content: text,
          thoughts,
          citations,
          assessment,
          duration: (Date.now() - startTime) / 1000,
        });

        // 【P0.1】从槽位提取到的患儿信息（如月龄）同步更新档案
        if (Object.keys(finalSlots).length > 0) {
          await this.patientService.upsertFromSlots(userId, finalSlots);
        }

        // 【P0.1】将本轮 AI 回复的前 200 字作为问诊摘要追加到档案历史
        if (text.trim().length > 20) {
          // 去掉 think 标签内容，只保留正式回复摘要
          const cleanText = text.replace(/<think>[\s\S]*?<\/think>/i, '').trim();
          const structuredSummary = typeof assessment?.summaryText === 'string' ? assessment.summaryText : '';
          if (structuredSummary) {
            await this.patientService.appendMedicalHistory(userId, structuredSummary);
          } else if (cleanText.length > 0) {
            await this.patientService.appendMedicalHistory(userId, cleanText.slice(0, 200));
          }
        }

        // 【P0.1 & P0.2】如果本轮有 OCR 结果，更新化验单摘要
        if (ocrResult) {
          await this.patientService.updateLastOcrSummary(userId, ocrResult);
        }

        const qualityLog = {
          event: 'chat_quality_summary',
          sessionId,
          userId,
          hasFollowupCard: Boolean(finalSlots && finalSlots.status === 'missing'),
          hasAssessment: Boolean(assessment),
          triageLevel: assessment?.triageLevel ?? null,
          trendDirection: assessment?.trendDirection ?? null,
          hasStructuredSummary: Boolean(assessment?.summaryText),
          evidenceLayerCount: Array.isArray(assessment?.evidenceLayers) ? assessment.evidenceLayers.length : 0,
          citationCount: citations.length,
          thoughtCount: thoughts.length,
          durationSeconds: (Date.now() - startTime) / 1000,
        };
        this.logger.log(JSON.stringify(qualityLog));
      });

      return response.data as NodeJS.ReadableStream;
    } catch (error: unknown) {
      const err = error as Error;
      this.logger.error(err.message, err.stack);
      throw new InternalServerErrorException({ message: 'AI 流式通信失败', detail: err.message });
    }
  }

  async uploadImage(
    userId: string,
    file: UploadedBinaryFile,
  ): Promise<{ fileId: string; url: string }> {
    if (!file) {
      throw new InternalServerErrorException('未接收到文件');
    }

    const formData = new FormData();
    formData.append('userId', userId);
    const bytes = new Uint8Array(file.buffer);
    formData.append('file', new Blob([bytes], { type: file.mimetype }), file.originalname);

    const response = await fetch(`${this.aiEngineUrl}/internal/upload`, {
      method: 'POST',
      headers: {
        'x-internal-token': this.aiEngineInternalToken,
      },
      body: formData,
    });

    if (!response.ok) {
      throw new InternalServerErrorException('图片上传失败');
    }

    const payload = await response.json() as { storageKey: string };
    const saved = await this.uploadedImageRepository.save(
      this.uploadedImageRepository.create({
        userId,
        storageKey: payload.storageKey,
        originalName: file.originalname,
        mimeType: file.mimetype || 'application/octet-stream',
      }),
    );

    return {
      fileId: saved.id,
      url: `${this.configService.get<string>('BFF_PUBLIC_BASE_URL', 'http://127.0.0.1:3000')}/api/v1/chat/files/${saved.id}`,
    };
  }

  async getImageForUser(
    userId: string,
    fileId: string,
  ): Promise<{ mimeType: string; buffer: Buffer }> {
    const file = await this.uploadedImageRepository.findOne({ where: { id: fileId, userId } });
    if (!file) {
      throw new InternalServerErrorException('图片不存在或无权访问');
    }

    const response = await fetch(`${this.aiEngineUrl}/internal/files/${file.storageKey}`, {
      headers: {
        'x-internal-token': this.aiEngineInternalToken,
      },
    });
    if (!response.ok) {
      throw new InternalServerErrorException('读取图片失败');
    }

    const arrayBuffer = await response.arrayBuffer();
    return {
      mimeType: file.mimeType,
      buffer: Buffer.from(arrayBuffer),
    };
  }

  private async resolveInternalImageRef(userId: string, fileId: string): Promise<string> {
    const file = await this.uploadedImageRepository.findOne({ where: { id: fileId, userId } });
    if (!file) {
      throw new InternalServerErrorException('图片不存在或无权访问');
    }
    return `private://${file.storageKey}`;
  }
}
