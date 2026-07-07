import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { ChatController } from './chat.controller';
import { ChatService } from './chat.service';
import { CryptoService } from '../common/services/crypto.service';
import { PatientModule } from '../patient/patient.module';

import { TypeOrmModule } from '@nestjs/typeorm';
import { ChatSessionEntity } from '../database/entities/chat-session.entity';
import { ChatMessageEntity } from '../database/entities/chat-message.entity';
import { UploadedImageEntity } from '../database/entities/uploaded-image.entity';

@Module({
  imports: [
    HttpModule,
    PatientModule,
    TypeOrmModule.forFeature([ChatSessionEntity, ChatMessageEntity, UploadedImageEntity])
  ],
  controllers: [ChatController],
  providers: [ChatService, CryptoService],
})
export class ChatModule {}
