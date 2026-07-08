import { Entity, Column, ManyToOne, JoinColumn, Index } from 'typeorm';
import { BaseEntity } from './base.entity';
import { UserEntity } from './user.entity';
import { CryptoService } from '../../common/services/crypto.service';

@Entity('patient_profiles')
export class PatientProfileEntity extends BaseEntity {
  @ManyToOne(() => UserEntity, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'user_id' })
  user: UserEntity;

  @Column({ name: 'user_id' })
  userId: string;

  // 昵称使用不可逆 Hash，不存明文
  @Column({ name: 'nickname_hash', type: 'varchar', length: 64 })
  nicknameHash: string;

  @Column({ name: 'display_name_encrypted', type: 'text', nullable: true })
  displayNameEncrypted: string | null;

  @Column({ name: 'birthday', type: 'date' })
  birthday: Date;

  @Column({ name: 'gender', type: 'smallint', comment: '1=男 2=女 0=未知' })
  gender: number;

  // 过敏史：AES-256 加密存储（密文）
  @Column({ name: 'known_allergens_encrypted', type: 'text', nullable: true })
  knownAllergensEncrypted: string | null;

  // 历次问诊摘要（AES-256 加密）：每轮问诊后由 AI 自动生成一段摘要并 append
  @Column({ name: 'medical_history_encrypted', type: 'text', nullable: true })
  medicalHistoryEncrypted: string | null;

  // 最近一次化验单摘要（AES-256 加密）：由 OCR 结构化数据提炼，供下次就诊快速引用
  @Column({ name: 'last_ocr_summary_encrypted', type: 'text', nullable: true })
  lastOcrSummaryEncrypted: string | null;

  // --------- 运行时虚拟字段（不持久化）---------
  knownAllergens?: string;
  medicalHistory?: string;
  lastOcrSummary?: string;
  displayName?: string;

  encryptSensitiveFields(cryptoService: CryptoService) {
    if (this.displayName) {
      this.displayNameEncrypted = cryptoService.encrypt(this.displayName);
      delete this.displayName;
    }
    if (this.knownAllergens) {
      this.knownAllergensEncrypted = cryptoService.encrypt(this.knownAllergens);
      delete this.knownAllergens;
    }
    if (this.medicalHistory) {
      this.medicalHistoryEncrypted = cryptoService.encrypt(this.medicalHistory);
      delete this.medicalHistory;
    }
    if (this.lastOcrSummary) {
      this.lastOcrSummaryEncrypted = cryptoService.encrypt(this.lastOcrSummary);
      delete this.lastOcrSummary;
    }
  }

  decryptSensitiveFields(cryptoService: CryptoService) {
    if (this.displayNameEncrypted) {
      this.displayName = cryptoService.decrypt(this.displayNameEncrypted);
    }
    if (this.knownAllergensEncrypted) {
      this.knownAllergens = cryptoService.decrypt(this.knownAllergensEncrypted);
    }
    if (this.medicalHistoryEncrypted) {
      this.medicalHistory = cryptoService.decrypt(this.medicalHistoryEncrypted);
    }
    if (this.lastOcrSummaryEncrypted) {
      this.lastOcrSummary = cryptoService.decrypt(this.lastOcrSummaryEncrypted);
    }
  }
}
