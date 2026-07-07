import { Entity, Column, ManyToOne, JoinColumn, Index } from 'typeorm';
import { BaseEntity } from './base.entity';
import { ChatSessionEntity } from './chat-session.entity';

export type SenderType = 'user' | 'ai';
export type IntentType = 'medical' | 'report' | 'general';

@Entity('chat_messages')
export class ChatMessageEntity extends BaseEntity {
  @ManyToOne(() => ChatSessionEntity, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'session_id' })
  session: ChatSessionEntity;

  @Index()
  @Column({ name: 'session_id' })
  sessionId: string;

  @Column({ name: 'sender', type: 'varchar', length: 10 })
  sender: SenderType;

  // 消息内容（大文本）
  @Column({ name: 'content', type: 'text' })
  content: string;

  // 可选的图片URL（用于多模态）
  @Column({ name: 'image_url', type: 'varchar', nullable: true })
  imageUrl: string | null;

  // AI 深度思考的过程
  @Column({ name: 'thoughts', type: 'jsonb', nullable: true })
  thoughts: string[] | null;

  // 耗时（秒）
  @Column({ name: 'duration', type: 'numeric', nullable: true })
  duration: number | null;

  // 意图分类结果
  @Column({ name: 'intent', type: 'varchar', length: 20, nullable: true })
  intent: IntentType | null;

  // RAG 来源引用（JSONB 格式，支持富文本查询）
  @Column({ name: 'citations', type: 'jsonb', nullable: true })
  citations: any[] | null;

  // 链路追踪 ID（与 BFF 日志关联）
  @Column({ name: 'trace_id', type: 'varchar', length: 64, nullable: true })
  traceId: string | null;
}
