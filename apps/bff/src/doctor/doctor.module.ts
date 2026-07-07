import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DoctorController } from './doctor.controller';
import { DoctorService } from './doctor.service';
import { CryptoService } from '../common/services/crypto.service';
import { ChatMessageEntity } from '../database/entities/chat-message.entity';
import { ChatSessionEntity } from '../database/entities/chat-session.entity';
import { DietaryRecordEntity } from '../database/entities/dietary-record.entity';
import { PatientProfileEntity } from '../database/entities/patient-profile.entity';

@Module({
  imports: [
    TypeOrmModule.forFeature([
      ChatSessionEntity,
      ChatMessageEntity,
      PatientProfileEntity,
      DietaryRecordEntity,
    ]),
  ],
  controllers: [DoctorController],
  providers: [DoctorService, CryptoService],
})
export class DoctorModule {}
