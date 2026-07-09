import { Column, Entity, Index, JoinColumn, ManyToOne } from 'typeorm';
import { BaseEntity } from './base.entity';
import { UserEntity } from './user.entity';

@Entity('growth_records')
export class GrowthRecordEntity extends BaseEntity {
  @ManyToOne(() => UserEntity, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'user_id' })
  user: UserEntity;

  @Index()
  @Column({ name: 'user_id' })
  userId: string;

  @Column({ name: 'age_months', type: 'smallint' })
  ageMonths: number;

  @Column({ name: 'weight', type: 'numeric', precision: 5, scale: 2 })
  weight: number;

  @Column({ name: 'height', type: 'numeric', precision: 5, scale: 2, nullable: true })
  height: number | null;
}
