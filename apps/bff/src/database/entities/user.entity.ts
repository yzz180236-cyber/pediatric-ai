import { Entity, Column, Index, OneToMany } from 'typeorm';
import { BaseEntity } from './base.entity';
import { PatientProfileEntity } from './patient-profile.entity';
import { DietaryRecordEntity } from './dietary-record.entity';
import type { AuthSource } from '@pediatric-ai/shared-types';

export type UserRole = 'user' | 'doctor';

@Entity('users')
export class UserEntity extends BaseEntity {
  // 微信 openid，全局唯一索引
  @Index({ unique: true })
  @Column({ name: 'openid', type: 'varchar', length: 64 })
  openid: string;

  @Column({ name: 'auth_source', type: 'varchar', length: 16, default: 'wechat' })
  authSource: AuthSource;

  @Column({ name: 'role', type: 'varchar', length: 16, default: 'user' })
  role: UserRole;

  @Index({ unique: true, where: 'dev_username IS NOT NULL' })
  @Column({ name: 'dev_username', type: 'varchar', length: 64, nullable: true })
  devUsername: string | null;

  // 微信 unionid（多平台打通用）
  @Column({ name: 'unionid', type: 'varchar', length: 64, nullable: true })
  unionid: string | null;

  // 最后登录时间
  @Column({ name: 'last_login_at', type: 'timestamptz', nullable: true })
  lastLoginAt: Date | null;

  @OneToMany(() => PatientProfileEntity, (profile) => profile.user)
  profiles: PatientProfileEntity[];

  @OneToMany(() => DietaryRecordEntity, (record) => record.user)
  dietaryRecords: DietaryRecordEntity[];
}
