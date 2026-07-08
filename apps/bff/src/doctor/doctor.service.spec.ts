import { Repository, ObjectLiteral } from 'typeorm';
import { ChatMessageEntity } from '../database/entities/chat-message.entity';
import { ChatSessionEntity } from '../database/entities/chat-session.entity';
import { DietaryRecordEntity } from '../database/entities/dietary-record.entity';
import { PatientProfileEntity } from '../database/entities/patient-profile.entity';
import { DoctorService } from './doctor.service';
import { CryptoService } from '../common/services/crypto.service';

function createRepoMock<T extends ObjectLiteral>() {
  return {
    find: jest.fn(),
    findOne: jest.fn(),
  } as unknown as jest.Mocked<Repository<T>>;
}

describe('DoctorService', () => {
  it('builds workbench summary from sessions and dietary alerts', async () => {
    const sessionRepo = createRepoMock<ChatSessionEntity>();
    const messageRepo = createRepoMock<ChatMessageEntity>();
    const profileRepo = createRepoMock<PatientProfileEntity>();
    const dietaryRepo = createRepoMock<DietaryRecordEntity>();

    sessionRepo.find.mockResolvedValue([
      {
        id: 'session-1',
        userId: 'user-1',
        lastActiveAt: new Date('2026-07-07T00:00:00.000Z'),
      },
    ] as ChatSessionEntity[]);
    messageRepo.findOne.mockResolvedValue({
      content: '宝宝今天发烧，体温 38.2 度',
      sender: 'user',
    } as ChatMessageEntity);
    profileRepo.findOne.mockResolvedValue({
      id: 'profile-1',
      userId: 'user-1',
      nicknameHash: 'hash',
      birthday: new Date('2025-03-01'),
      gender: 1,
      medicalHistoryEncrypted: null,
      lastOcrSummaryEncrypted: null,
      knownAllergensEncrypted: 'cipher',
      displayNameEncrypted: 'cipher',
      decryptSensitiveFields: jest.fn(function (this: any) {
        this.knownAllergens = '牛奶蛋白'
        this.displayName = '果果'
      }),
    } as unknown as PatientProfileEntity);
    dietaryRepo.find.mockResolvedValue([
      {
        id: 'dietary-1',
        userId: 'user-1',
        addedFood: '米粉',
        allergyWarning: '少量尝试观察',
        createdAt: new Date('2026-07-07T01:00:00.000Z'),
      },
    ] as DietaryRecordEntity[]);

    const service = new DoctorService(sessionRepo, messageRepo, profileRepo, dietaryRepo, {} as CryptoService);
    const result = await service.getWorkbench();

    expect(result.summary).toEqual({
      totalSessions: 1,
      activePatients: 1,
      dietaryAlerts: 1,
    });
    expect(result.sessions[0].patientDisplayName).toBe('果果');
    expect(result.sessions[0].latestMessagePreview).toContain('宝宝今天发烧');
    expect(result.dietaryAlerts[0].addedFood).toBe('米粉');
  });

  it('returns patient profile with display name for doctor view', async () => {
    const sessionRepo = createRepoMock<ChatSessionEntity>();
    const messageRepo = createRepoMock<ChatMessageEntity>();
    const profileRepo = createRepoMock<PatientProfileEntity>();
    const dietaryRepo = createRepoMock<DietaryRecordEntity>();

    profileRepo.findOne.mockResolvedValue({
      id: 'profile-1',
      userId: 'user-1',
      nicknameHash: 'hash',
      birthday: new Date('2025-03-01'),
      gender: 1,
      medicalHistoryEncrypted: null,
      lastOcrSummaryEncrypted: null,
      decryptSensitiveFields: jest.fn(function (this: any) {
        this.displayName = '果果'
        this.knownAllergens = '牛奶蛋白'
        this.medicalHistory = '摘要'
        this.lastOcrSummary = '化验单摘要'
      }),
    } as unknown as PatientProfileEntity);

    const service = new DoctorService(sessionRepo, messageRepo, profileRepo, dietaryRepo, {} as CryptoService);
    const result = await service.getPatientProfile('user-1');

    expect(result.displayName).toBe('果果');
    expect(result.knownAllergens).toBe('牛奶蛋白');
  });
});
