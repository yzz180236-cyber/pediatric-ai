import { BadRequestException, NotFoundException } from '@nestjs/common';
import { Repository } from 'typeorm';
import { DietaryRecordEntity } from '../database/entities/dietary-record.entity';
import { CryptoService } from '../common/services/crypto.service';
import { GrowthRecordEntity } from '../database/entities/growth-record.entity';
import { PatientProfileEntity } from '../database/entities/patient-profile.entity';
import { PatientService } from './patient.service';

function createRepoMock<T>() {
  return {
    find: jest.fn(),
    findOne: jest.fn(),
    create: jest.fn(),
    save: jest.fn(),
    delete: jest.fn(),
  } as unknown as jest.Mocked<Repository<T>>;
}

describe('PatientService growth records', () => {
  let service: PatientService;
  let patientProfileRepo: jest.Mocked<Repository<PatientProfileEntity>>;
  let dietaryRecordRepo: jest.Mocked<Repository<DietaryRecordEntity>>;
  let growthRecordRepo: jest.Mocked<Repository<GrowthRecordEntity>>;

  beforeEach(() => {
    patientProfileRepo = createRepoMock<PatientProfileEntity>();
    dietaryRecordRepo = createRepoMock<DietaryRecordEntity>();
    growthRecordRepo = createRepoMock<GrowthRecordEntity>();

    service = new PatientService(
      patientProfileRepo,
      dietaryRecordRepo,
      growthRecordRepo,
      {} as CryptoService,
    );
  });

  it('adds a growth record with normalized age months', async () => {
    growthRecordRepo.create.mockImplementation((value) => value as GrowthRecordEntity);
    growthRecordRepo.save.mockResolvedValue({
      id: 'record-1',
      ageMonths: 4,
      weight: 6.8,
      createdAt: new Date('2026-07-07T00:00:00.000Z'),
    } as GrowthRecordEntity);

    const result = await service.addGrowthRecord('user-1', {
      ageMonths: 4,
      weight: 6.8,
    });

    expect(growthRecordRepo.create).toHaveBeenCalledWith({
      userId: 'user-1',
      ageMonths: 4,
      weight: 6.8,
    });
    expect(result).toEqual({
      id: 'record-1',
      ageMonths: 4,
      monthLabel: '4月龄',
      weight: 6.8,
      createdAt: '2026-07-07T00:00:00.000Z',
    });
  });

  it('rejects invalid age months', async () => {
    await expect(
      service.addGrowthRecord('user-1', {
        ageMonths: 100,
        weight: 6.8,
      }),
    ).rejects.toBeInstanceOf(BadRequestException);
  });

  it('updates an existing growth record', async () => {
    growthRecordRepo.findOne.mockResolvedValue({
      id: 'record-1',
      userId: 'user-1',
      ageMonths: 3,
      weight: 5.5,
      createdAt: new Date('2026-07-06T00:00:00.000Z'),
    } as GrowthRecordEntity);
    growthRecordRepo.save.mockImplementation(async (value) => ({
      ...(value as object),
      createdAt: new Date('2026-07-06T00:00:00.000Z'),
    } as GrowthRecordEntity));

    const result = await service.updateGrowthRecord('user-1', 'record-1', {
      ageMonths: 5,
      weight: 7.1,
    });

    expect(result.ageMonths).toBe(5);
    expect(result.monthLabel).toBe('5月龄');
    expect(result.weight).toBe(7.1);
  });

  it('throws when deleting a missing growth record', async () => {
    growthRecordRepo.delete.mockResolvedValue({ affected: 0, raw: {} } as never);

    await expect(service.deleteGrowthRecord('user-1', 'missing')).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('stores dietary records structurally', async () => {
    const profile = {
      id: 'profile-1',
      userId: 'user-1',
      birthday: new Date('2025-01-01'),
      gender: 0,
      decryptSensitiveFields: jest.fn(),
      encryptSensitiveFields: jest.fn(),
      knownAllergens: '',
    } as unknown as PatientProfileEntity;

    patientProfileRepo.findOne.mockResolvedValue(profile);
    dietaryRecordRepo.create.mockImplementation((value) => value as DietaryRecordEntity);
    dietaryRecordRepo.save.mockResolvedValue({ id: 'dietary-1' } as DietaryRecordEntity);
    patientProfileRepo.save.mockResolvedValue(profile);

    const result = await service.addDietaryRecord('user-1', {
      recommendation: '含铁米粉',
      allergy_warning: '少量尝试',
      added_food: '米粉',
    });

    expect(dietaryRecordRepo.create).toHaveBeenCalledWith({
      userId: 'user-1',
      recommendation: '含铁米粉',
      allergyWarning: '少量尝试',
      addedFood: '米粉',
    });
    expect(result).toEqual({ status: 'success', message: '辅食排敏记录已归档' });
  });

  it('lists dietary records in reverse chronological order', async () => {
    dietaryRecordRepo.find.mockResolvedValue([
      {
        id: 'dietary-1',
        recommendation: '含铁米粉',
        allergyWarning: '少量尝试',
        addedFood: '米粉',
        createdAt: new Date('2026-07-07T00:00:00.000Z'),
      },
    ] as DietaryRecordEntity[]);

    const result = await service.listDietaryRecords('user-1');

    expect(result).toEqual([
      {
        id: 'dietary-1',
        recommendation: '含铁米粉',
        allergyWarning: '少量尝试',
        addedFood: '米粉',
        createdAt: '2026-07-07T00:00:00.000Z',
      },
    ]);
  });

  it('throws when deleting a missing dietary record', async () => {
    dietaryRecordRepo.delete.mockResolvedValue({ affected: 0, raw: {} } as never);

    await expect(service.deleteDietaryRecord('user-1', 'missing')).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('updates dietary records structurally', async () => {
    dietaryRecordRepo.findOne.mockResolvedValue({
      id: 'dietary-1',
      userId: 'user-1',
      recommendation: '含铁米粉',
      allergyWarning: '少量尝试',
      addedFood: '米粉',
      createdAt: new Date('2026-07-07T00:00:00.000Z'),
    } as DietaryRecordEntity);
    dietaryRecordRepo.save.mockImplementation(async (value) => value as DietaryRecordEntity);

    const result = await service.updateDietaryRecord('user-1', 'dietary-1', {
      recommendation: '高铁米粉',
      allergyWarning: '先喂一勺观察',
      addedFood: '高铁米粉',
    });

    expect(result).toEqual({
      id: 'dietary-1',
      recommendation: '高铁米粉',
      allergyWarning: '先喂一勺观察',
      addedFood: '高铁米粉',
      createdAt: '2026-07-07T00:00:00.000Z',
    });
  });
});
