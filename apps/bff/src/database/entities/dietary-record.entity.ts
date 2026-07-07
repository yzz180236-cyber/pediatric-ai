import { Column, Entity, Index, JoinColumn, ManyToOne } from 'typeorm';
import { BaseEntity } from './base.entity';
import { UserEntity } from './user.entity';

@Entity('dietary_records')
export class DietaryRecordEntity extends BaseEntity {
  @ManyToOne(() => UserEntity, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'user_id' })
  user: UserEntity;

  @Index()
  @Column({ name: 'user_id' })
  userId: string;

  @Column({ name: 'recommendation', type: 'text' })
  recommendation: string;

  @Column({ name: 'allergy_warning', type: 'text' })
  allergyWarning: string;

  @Column({ name: 'added_food', type: 'varchar', length: 128 })
  addedFood: string;
}
