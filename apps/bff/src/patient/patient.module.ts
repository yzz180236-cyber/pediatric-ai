import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { PatientController } from './patient.controller';
import { PatientService } from './patient.service';
import { PatientProfileEntity } from '../database/entities/patient-profile.entity';
import { GrowthRecordEntity } from '../database/entities/growth-record.entity';
import { DietaryRecordEntity } from '../database/entities/dietary-record.entity';
import { CryptoService } from '../common/services/crypto.service';

@Module({
  imports: [TypeOrmModule.forFeature([PatientProfileEntity, GrowthRecordEntity, DietaryRecordEntity])],
  controllers: [PatientController],
  providers: [PatientService, CryptoService],
  exports: [PatientService],
})
export class PatientModule {}
