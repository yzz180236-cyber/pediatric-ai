import { BadRequestException, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { PatientProfileEntity } from '../database/entities/patient-profile.entity';
import { CryptoService } from '../common/services/crypto.service';
import { DietaryRecordEntity } from '../database/entities/dietary-record.entity';
import { GrowthRecordEntity } from '../database/entities/growth-record.entity';
import {
  CreateGrowthRecordRequest,
  DietaryRecordDto,
  GrowthRecordDto,
  PatientProfileDto,
  UpdateDietaryRecordRequest,
  UpdateGrowthRecordRequest,
  UpdatePatientProfileRequest,
} from '@pediatric-ai/shared-types';

@Injectable()
export class PatientService {
  private readonly logger = new Logger(PatientService.name);

  constructor(
    @InjectRepository(PatientProfileEntity)
    private readonly patientProfileRepo: Repository<PatientProfileEntity>,
    @InjectRepository(DietaryRecordEntity)
    private readonly dietaryRecordRepo: Repository<DietaryRecordEntity>,
    @InjectRepository(GrowthRecordEntity)
    private readonly growthRecordRepo: Repository<GrowthRecordEntity>,
    private readonly cryptoService: CryptoService,
  ) {}

  async listGrowthRecords(userId: string): Promise<GrowthRecordDto[]> {
    const records = await this.growthRecordRepo.find({
      where: { userId },
      order: { ageMonths: 'ASC', createdAt: 'ASC' },
    });

    return records.map((record) => ({
      id: record.id,
      ageMonths: record.ageMonths,
      monthLabel: `${record.ageMonths}月龄`,
      weight: Number(record.weight),
      createdAt: record.createdAt.toISOString(),
    }));
  }

  async getProfile(userId: string): Promise<PatientProfileDto> {
    const profile = await this.getOrCreateProfile(userId);
    profile.decryptSensitiveFields(this.cryptoService);
    return this.toProfileDto(profile);
  }

  async listDietaryRecords(userId: string): Promise<DietaryRecordDto[]> {
    const records = await this.dietaryRecordRepo.find({
      where: { userId },
      order: { createdAt: 'DESC' },
    });

    return records.map((record) => ({
      id: record.id,
      recommendation: record.recommendation,
      allergyWarning: record.allergyWarning,
      addedFood: record.addedFood,
      createdAt: record.createdAt.toISOString(),
    }));
  }

  async deleteDietaryRecord(userId: string, recordId: string): Promise<void> {
    const result = await this.dietaryRecordRepo.delete({ id: recordId, userId });
    if (!result.affected) {
      throw new NotFoundException('排敏记录不存在');
    }
  }

  async updateDietaryRecord(
    userId: string,
    recordId: string,
    data: UpdateDietaryRecordRequest,
  ): Promise<DietaryRecordDto> {
    const record = await this.dietaryRecordRepo.findOne({ where: { id: recordId, userId } });
    if (!record) {
      throw new NotFoundException('排敏记录不存在');
    }

    const recommendation = data.recommendation.trim();
    const allergyWarning = data.allergyWarning.trim();
    const addedFood = data.addedFood.trim();

    if (!recommendation || !allergyWarning || !addedFood) {
      throw new BadRequestException('排敏记录字段不能为空');
    }

    record.recommendation = recommendation;
    record.allergyWarning = allergyWarning;
    record.addedFood = addedFood;
    const savedRecord = await this.dietaryRecordRepo.save(record);

    return {
      id: savedRecord.id,
      recommendation: savedRecord.recommendation,
      allergyWarning: savedRecord.allergyWarning,
      addedFood: savedRecord.addedFood,
      createdAt: savedRecord.createdAt.toISOString(),
    };
  }

  async addGrowthRecord(userId: string, data: CreateGrowthRecordRequest): Promise<GrowthRecordDto> {
    const { ageMonths, weight } = this.validateGrowthRecord(data);

    const record = this.growthRecordRepo.create({
      userId,
      ageMonths,
      weight,
    });
    const savedRecord = await this.growthRecordRepo.save(record);

    return {
      id: savedRecord.id,
      ageMonths: savedRecord.ageMonths,
      monthLabel: `${savedRecord.ageMonths}月龄`,
      weight: Number(savedRecord.weight),
      createdAt: savedRecord.createdAt.toISOString(),
    };
  }

  async updateGrowthRecord(
    userId: string,
    recordId: string,
    data: UpdateGrowthRecordRequest,
  ): Promise<GrowthRecordDto> {
    const record = await this.growthRecordRepo.findOne({ where: { id: recordId, userId } });
    if (!record) {
      throw new NotFoundException('生长记录不存在');
    }

    const { ageMonths, weight } = this.validateGrowthRecord(data);
    record.ageMonths = ageMonths;
    record.weight = weight;
    const savedRecord = await this.growthRecordRepo.save(record);

    return {
      id: savedRecord.id,
      ageMonths: savedRecord.ageMonths,
      monthLabel: `${savedRecord.ageMonths}月龄`,
      weight: Number(savedRecord.weight),
      createdAt: savedRecord.createdAt.toISOString(),
    };
  }

  async deleteGrowthRecord(userId: string, recordId: string): Promise<void> {
    const result = await this.growthRecordRepo.delete({ id: recordId, userId });
    if (!result.affected) {
      throw new NotFoundException('生长记录不存在');
    }
  }

  async updateProfile(
    userId: string,
    data: UpdatePatientProfileRequest,
  ): Promise<PatientProfileDto> {
    const profile = await this.getOrCreateProfile(userId);
    profile.decryptSensitiveFields(this.cryptoService);

    const birthday = new Date(data.birthday);
    if (Number.isNaN(birthday.getTime())) {
      throw new BadRequestException('生日格式无效');
    }
    if (![0, 1, 2].includes(data.gender)) {
      throw new BadRequestException('性别字段无效');
    }
    const displayName = data.displayName.trim();
    if (!displayName) {
      throw new BadRequestException('宝宝昵称不能为空');
    }

    profile.birthday = birthday;
    profile.gender = data.gender;
    profile.displayName = displayName;
    profile.knownAllergens = data.knownAllergens.trim();
    profile.encryptSensitiveFields(this.cryptoService);
    const savedProfile = await this.patientProfileRepo.save(profile);
    savedProfile.decryptSensitiveFields(this.cryptoService);
    return this.toProfileDto(savedProfile);
  }

  private validateGrowthRecord(
    data: CreateGrowthRecordRequest | UpdateGrowthRecordRequest,
  ): { ageMonths: number; weight: number } {
    const ageMonths = Number(data.ageMonths);
    const weight = Number(data.weight);

    if (!Number.isInteger(ageMonths) || ageMonths < 0 || ageMonths > 72) {
      throw new BadRequestException('月龄必须是 0-72 之间的整数');
    }

    if (!Number.isFinite(weight) || weight <= 0) {
      throw new BadRequestException('体重必须是大于 0 的数字');
    }
    return { ageMonths, weight };
  }

  private toProfileDto(profile: PatientProfileEntity): PatientProfileDto {
    return {
      id: profile.id,
      userId: profile.userId,
      displayName: profile.displayName ?? '未命名宝宝',
      birthday: new Date(profile.birthday).toISOString().slice(0, 10),
      gender: profile.gender,
      knownAllergens: profile.knownAllergens ?? '',
      medicalHistory: profile.medicalHistory ?? '',
      lastOcrSummary: profile.lastOcrSummary ?? '',
    };
  }

  /**
   * 获取或创建用户的患儿档案（内部方法，自动建档兜底）
   */
  private async getOrCreateProfile(userId: string): Promise<PatientProfileEntity> {
    let profile = await this.patientProfileRepo.findOne({ where: { userId } });
    if (!profile) {
      // 自动建档：首次使用时创建空白档案
      profile = this.patientProfileRepo.create({
        userId,
        nicknameHash: 'unknown',
        displayName: '未命名宝宝',
        birthday: new Date('2020-01-01'),
        gender: 0,
      });
      await this.patientProfileRepo.save(profile);
      this.logger.log(`为用户 ${userId.slice(0, 8)} 自动创建了患儿档案`);
    }
    return profile;
  }

  /**
   * 读取患儿档案，返回格式化为 AI 可读的纯文字摘要
   * 此摘要将注入 chat_node 的 system_prompt，让大模型"认识"这个孩子
   */
  async getProfileSummary(userId: string): Promise<string> {
    try {
      const profile = await this.patientProfileRepo.findOne({ where: { userId } });
      if (!profile) return '';

      profile.decryptSensitiveFields(this.cryptoService);

      const lines: string[] = ['【患儿档案（跨会话记忆）】'];

      if (profile.displayName) {
        lines.push(`- 宝宝称呼：${profile.displayName}`);
      }

      if (profile.birthday) {
        const now = new Date();
        const birth = new Date(profile.birthday);
        const ageMonths = Math.floor(
          (now.getTime() - birth.getTime()) / (1000 * 60 * 60 * 24 * 30.44)
        );
        if (ageMonths < 24) {
          lines.push(`- 月龄：${ageMonths} 个月`);
        } else {
          lines.push(`- 年龄：${Math.floor(ageMonths / 12)} 岁`);
        }
      }

      const latestGrowthRecord = await this.growthRecordRepo.findOne({
        where: { userId },
        order: { ageMonths: 'DESC', createdAt: 'DESC' },
      });
      if (latestGrowthRecord) {
        lines.push(`- 最近体重：${Number(latestGrowthRecord.weight)} kg（${latestGrowthRecord.ageMonths} 月龄记录）`);
      }

      if (profile.gender) {
        lines.push(`- 性别：${profile.gender === 1 ? '男' : profile.gender === 2 ? '女' : '未知'}`);
      }

      if (profile.knownAllergens) {
        lines.push(`- 已知过敏史：${profile.knownAllergens}`);
      } else {
        lines.push('- 已知过敏史：无记录');
      }

      if (profile.medicalHistory) {
        const trimmed = profile.medicalHistory.slice(-500);
        lines.push(`- 近期就诊记录摘要：\n${trimmed}`);
      }

      if (profile.lastOcrSummary) {
        lines.push(`- 最近一次化验单摘要：${profile.lastOcrSummary}`);
      }

      return lines.join('\n');
    } catch (error: unknown) {
      const err = error as Error;
      this.logger.error('读取患儿档案失败: ' + err.message);
      return '';
    }
  }

  async getClinicalContext(userId: string): Promise<Record<string, unknown>> {
    try {
      const profile = await this.getOrCreateProfile(userId);
      profile.decryptSensitiveFields(this.cryptoService);

      const latestGrowthRecord = await this.growthRecordRepo.findOne({
        where: { userId },
        order: { ageMonths: 'DESC', createdAt: 'DESC' },
      });

      const now = new Date();
      const birth = new Date(profile.birthday);
      const ageMonths = Number.isNaN(birth.getTime())
        ? null
        : Math.max(0, Math.floor((now.getTime() - birth.getTime()) / (1000 * 60 * 60 * 24 * 30.44)));

      return {
        displayName: profile.displayName ?? '未命名宝宝',
        ageMonths,
        ageYears: ageMonths !== null ? Number((ageMonths / 12).toFixed(1)) : null,
        gender: profile.gender,
        knownAllergens: profile.knownAllergens
          ? profile.knownAllergens
              .split(/[、,，\s]+/)
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
        latestWeightKg: latestGrowthRecord ? Number(latestGrowthRecord.weight) : null,
        latestWeightAgeMonths: latestGrowthRecord?.ageMonths ?? null,
        hasCompleteProfile: Boolean(profile.displayName && profile.birthday && profile.gender !== undefined),
      };
    } catch (error: unknown) {
      const err = error as Error;
      this.logger.error('读取患儿结构化上下文失败: ' + err.message);
      return {};
    }
  }

  /**
   * 当 AI 从对话中提取到新的槽位信息时（如月龄），自动更新患儿档案
   */
  async upsertFromSlots(userId: string, slots: Record<string, string>): Promise<void> {
    try {
      if (!slots || Object.keys(slots).filter(k => k !== 'status' && k !== '_last_update').length === 0) return;
      const profile = await this.getOrCreateProfile(userId);
      profile.decryptSensitiveFields(this.cryptoService);

      const ageStr = slots['age'] || slots['月龄'] || slots['年龄'] || '';
      if (ageStr) {
        const monthMatch = ageStr.match(/(\d+)\s*[个]?\s*月/);
        const yearMatch = ageStr.match(/(\d+)\s*[岁年]/);
        if (monthMatch) {
          const months = parseInt(monthMatch[1]);
          const birth = new Date();
          birth.setMonth(birth.getMonth() - months);
          profile.birthday = birth;
        } else if (yearMatch) {
          const years = parseInt(yearMatch[1]);
          const birth = new Date();
          birth.setFullYear(birth.getFullYear() - years);
          profile.birthday = birth;
        }
      }

      const genderStr = slots['gender'] || slots['性别'] || '';
      if (genderStr.includes('男')) profile.gender = 1;
      else if (genderStr.includes('女')) profile.gender = 2;

      profile.encryptSensitiveFields(this.cryptoService);
      await this.patientProfileRepo.save(profile);
      this.logger.log(`已从槽位更新用户 ${userId.slice(0, 8)} 的患儿档案`);
    } catch (error: unknown) {
      const err = error as Error;
      this.logger.error('从槽位更新档案失败: ' + err.message);
    }
  }

  /**
   * 每轮问诊结束后，将本轮摘要 append 到医疗历史
   */
  async appendMedicalHistory(userId: string, summary: string): Promise<void> {
    try {
      if (!summary.trim()) return;
      const profile = await this.getOrCreateProfile(userId);
      profile.decryptSensitiveFields(this.cryptoService);

      const timestamp = new Date().toLocaleDateString('zh-CN');
      const newEntry = `[${timestamp}] ${summary.slice(0, 200)}`;
      profile.medicalHistory = profile.medicalHistory
        ? profile.medicalHistory + '\n' + newEntry
        : newEntry;

      // 总长度控制在 2000 字以内，超出则保留最近 10 条
      if (profile.medicalHistory.length > 2000) {
        const entries = profile.medicalHistory.split('\n');
        profile.medicalHistory = entries.slice(-10).join('\n');
      }

      profile.encryptSensitiveFields(this.cryptoService);
      await this.patientProfileRepo.save(profile);
    } catch (error: unknown) {
      const err = error as Error;
      this.logger.error('追加问诊摘要失败: ' + err.message);
    }
  }

  /**
   * 化验单 OCR 完成后，将关键指标摘要写入档案
   */
  async updateLastOcrSummary(userId: string, ocrResult: Record<string, unknown>): Promise<void> {
    try {
      if (!ocrResult || !ocrResult['items']) return;
      const profile = await this.getOrCreateProfile(userId);
      profile.decryptSensitiveFields(this.cryptoService);

      const items = ocrResult['items'] as Array<Record<string, unknown>>;
      const abnormalItems = items
        .filter((item) => item['isAbnormal'])
        .map((item) => `${item['name']}=${item['result']}${item['unit'] || ''}(参考:${item['referenceRange'] || ''})`);

      const date = (ocrResult['date'] as string) || new Date().toLocaleDateString('zh-CN');
      const hospital = (ocrResult['hospitalName'] as string) || '未知医院';
      profile.lastOcrSummary = `${date} ${hospital} - 异常指标: ${abnormalItems.length > 0 ? abnormalItems.join(', ') : '无'}`;

      profile.encryptSensitiveFields(this.cryptoService);
      await this.patientProfileRepo.save(profile);
      this.logger.log(`已更新用户 ${userId.slice(0, 8)} 的最近化验单摘要`);
    } catch (error: unknown) {
      const err = error as Error;
      this.logger.error('更新化验单摘要失败: ' + err.message);
    }
  }

  async addDietaryRecord(userId: string, data: Record<string, string>): Promise<{ status: string; message: string }> {
    const profile = await this.getOrCreateProfile(userId);
    profile.decryptSensitiveFields(this.cryptoService);

    const addedFood = (data.added_food || '未知').trim();
    const recommendation = (data.recommendation || '').trim();
    const allergyWarning = (data.allergy_warning || '').trim();

    if (!recommendation || !allergyWarning) {
      throw new BadRequestException('辅食排敏记录缺少必要字段');
    }

    const dietaryRecord = this.dietaryRecordRepo.create({
      userId,
      recommendation,
      allergyWarning,
      addedFood,
    });
    await this.dietaryRecordRepo.save(dietaryRecord);

    const allergySummary = addedFood === '未知'
      ? `辅食排敏记录：${recommendation}（提示：${allergyWarning}）`
      : `辅食排敏记录：${addedFood}（提示：${allergyWarning}）`;
    profile.knownAllergens = profile.knownAllergens
      ? `${profile.knownAllergens}\n${allergySummary}`
      : allergySummary;

    profile.encryptSensitiveFields(this.cryptoService);
    await this.patientProfileRepo.save(profile);

    return { status: 'success', message: '辅食排敏记录已归档' };
  }
}
