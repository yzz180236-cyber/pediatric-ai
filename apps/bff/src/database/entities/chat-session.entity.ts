import { Entity, Column, ManyToOne, JoinColumn, OneToMany, Index } from 'typeorm';
import { BaseEntity } from './base.entity';
import { UserEntity } from './user.entity';
import { ChatMessageEntity } from './chat-message.entity';

export type ChatSessionStatus = 'active' | 'followup' | 'closed';

@Entity('chat_sessions')
export class ChatSessionEntity extends BaseEntity {
  @ManyToOne(() => UserEntity, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'user_id' })
  user: UserEntity;

  @Index()
  @Column({ name: 'user_id' })
  userId: string;

  // 最后活跃时间（用于过期 Session 的清理）
  @Column({ name: 'last_active_at', type: 'timestamptz' })
  lastActiveAt: Date;

  @Column({ name: 'status', type: 'varchar', length: 16, default: 'active' })
  status: ChatSessionStatus;

  @Column({ name: 'doctor_note', type: 'text', nullable: true })
  doctorNote: string | null;

  @OneToMany(() => ChatMessageEntity, (msg) => msg.session)
  messages: ChatMessageEntity[];
}
