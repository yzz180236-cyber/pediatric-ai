import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import {
  DoctorDietaryAlertDto,
  DoctorWorkbenchDto,
  DoctorWorkbenchMessageDto,
  UpdateDoctorSessionRequest,
  DoctorWorkbenchSessionDetailDto,
  DoctorWorkbenchSessionDto,
} from '@pediatric-ai/shared-types';
import { CryptoService } from '../common/services/crypto.service';
import { Repository } from 'typeorm';
import { ChatMessageEntity } from '../database/entities/chat-message.entity';
import { ChatSessionEntity } from '../database/entities/chat-session.entity';
import { DietaryRecordEntity } from '../database/entities/dietary-record.entity';
import { PatientProfileEntity } from '../database/entities/patient-profile.entity';

@Injectable()
export class DoctorService {
  constructor(
    @InjectRepository(ChatSessionEntity)
    private readonly sessionRepo: Repository<ChatSessionEntity>,
    @InjectRepository(ChatMessageEntity)
    private readonly messageRepo: Repository<ChatMessageEntity>,
    @InjectRepository(PatientProfileEntity)
    private readonly profileRepo: Repository<PatientProfileEntity>,
    @InjectRepository(DietaryRecordEntity)
    private readonly dietaryRepo: Repository<DietaryRecordEntity>,
    private readonly cryptoService: CryptoService,
  ) {}

  async getWorkbench(): Promise<DoctorWorkbenchDto> {
    const sessions = await this.sessionRepo.find({
      order: { lastActiveAt: 'DESC' },
      take: 10,
    });

    const sessionDtos: DoctorWorkbenchSessionDto[] = [];
    for (const session of sessions) {
      const latestMessage = await this.messageRepo.findOne({
        where: { sessionId: session.id },
        order: { createdAt: 'DESC' },
      });
      const profile = await this.profileRepo.findOne({
        where: { userId: session.userId },
      });

      sessionDtos.push({
        sessionId: session.id,
        patientUserId: session.userId,
        patientBirthday: profile?.birthday ? new Date(profile.birthday).toISOString().slice(0, 10) : '',
        patientGender: profile?.gender ?? 0,
        knownAllergens: profile?.knownAllergensEncrypted ? '已登记' : '',
        lastActiveAt: session.lastActiveAt.toISOString(),
        status: session.status,
        latestMessagePreview: latestMessage?.content?.slice(0, 80) ?? '暂无消息',
        latestMessageSender: latestMessage?.sender ?? 'unknown',
      });
    }

    const dietary = await this.dietaryRepo.find({
      order: { createdAt: 'DESC' },
      take: 10,
    });

    const dietaryAlerts: DoctorDietaryAlertDto[] = dietary.map((record) => ({
      recordId: record.id,
      patientUserId: record.userId,
      addedFood: record.addedFood,
      allergyWarning: record.allergyWarning,
      createdAt: record.createdAt.toISOString(),
    }));

    return {
      summary: {
        totalSessions: sessions.length,
        activePatients: new Set(sessions.map((item) => item.userId)).size,
        dietaryAlerts: dietaryAlerts.length,
      },
      sessions: sessionDtos,
      dietaryAlerts,
    };
  }

  async getSessionDetail(sessionId: string): Promise<DoctorWorkbenchSessionDetailDto> {
    const session = await this.sessionRepo.findOne({ where: { id: sessionId } });
    if (!session) {
      throw new Error('会话不存在');
    }

    const profile = await this.profileRepo.findOne({ where: { userId: session.userId } });
    if (profile) {
      profile.decryptSensitiveFields(this.cryptoService);
    }

    const messages = await this.messageRepo.find({
      where: { sessionId: session.id },
      order: { createdAt: 'ASC' },
    });

    const messageDtos: DoctorWorkbenchMessageDto[] = messages.map((message) => ({
      id: message.id,
      sender: message.sender,
      content: message.content,
      createdAt: message.createdAt.toISOString(),
    }));

    return {
      sessionId: session.id,
      patientUserId: session.userId,
      patientBirthday: profile?.birthday ? new Date(profile.birthday).toISOString().slice(0, 10) : '',
      patientGender: profile?.gender ?? 0,
      knownAllergens: profile?.knownAllergens ?? '',
      medicalHistory: profile?.medicalHistory ?? '',
      lastOcrSummary: profile?.lastOcrSummary ?? '',
      lastActiveAt: session.lastActiveAt.toISOString(),
      status: session.status,
      doctorNote: session.doctorNote ?? '',
      messages: messageDtos,
    };
  }

  async updateSession(sessionId: string, data: UpdateDoctorSessionRequest): Promise<DoctorWorkbenchSessionDetailDto> {
    const session = await this.sessionRepo.findOne({ where: { id: sessionId } });
    if (!session) {
      throw new Error('会话不存在');
    }

    session.status = data.status;
    session.doctorNote = data.doctorNote.trim();
    await this.sessionRepo.save(session);
    return this.getSessionDetail(sessionId);
  }
}
