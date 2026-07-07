import { Controller, Post, Body, UseGuards, Request, Get, Put, Delete, Param } from '@nestjs/common';
import type {
  CreateGrowthRecordRequest,
  DietaryRecordDto,
  GrowthRecordDto,
  PatientProfileDto,
  UpdateDietaryRecordRequest,
  UpdateGrowthRecordRequest,
  UpdatePatientProfileRequest,
} from '@pediatric-ai/shared-types';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { PatientService } from './patient.service';

class CreateGrowthRecordDto implements CreateGrowthRecordRequest {
  ageMonths: number;
  weight: number;
}

class UpdateGrowthRecordDto implements UpdateGrowthRecordRequest {
  ageMonths: number;
  weight: number;
}

class UpdatePatientProfileDto implements UpdatePatientProfileRequest {
  birthday: string;
  gender: number;
  knownAllergens: string;
}

class UpdateDietaryRecordDto implements UpdateDietaryRecordRequest {
  recommendation: string;
  allergyWarning: string;
  addedFood: string;
}

@Controller('patient')
export class PatientController {
  constructor(private readonly patientService: PatientService) {}

  @UseGuards(JwtAuthGuard)
  @Get('growth-records')
  async getGrowthRecords(@Request() req: any): Promise<GrowthRecordDto[]> {
    const userId = req.user.userId;
    return this.patientService.listGrowthRecords(userId);
  }

  @UseGuards(JwtAuthGuard)
  @Get('profile')
  async getProfile(@Request() req: any): Promise<PatientProfileDto> {
    const userId = req.user.userId;
    return this.patientService.getProfile(userId);
  }

  @UseGuards(JwtAuthGuard)
  @Get('dietary')
  async getDietaryRecords(@Request() req: any): Promise<DietaryRecordDto[]> {
    const userId = req.user.userId;
    return this.patientService.listDietaryRecords(userId);
  }

  @UseGuards(JwtAuthGuard)
  @Delete('dietary/:id')
  async deleteDietaryRecord(
    @Request() req: any,
    @Param('id') recordId: string,
  ): Promise<{ success: true }> {
    const userId = req.user.userId;
    await this.patientService.deleteDietaryRecord(userId, recordId);
    return { success: true };
  }

  @UseGuards(JwtAuthGuard)
  @Put('dietary/:id')
  async updateDietaryRecord(
    @Request() req: any,
    @Param('id') recordId: string,
    @Body() body: UpdateDietaryRecordDto,
  ): Promise<DietaryRecordDto> {
    const userId = req.user.userId;
    return this.patientService.updateDietaryRecord(userId, recordId, body);
  }

  @UseGuards(JwtAuthGuard)
  @Post('growth-records')
  async createGrowthRecord(
    @Request() req: any,
    @Body() body: CreateGrowthRecordDto,
  ): Promise<GrowthRecordDto> {
    const userId = req.user.userId;
    return this.patientService.addGrowthRecord(userId, body);
  }

  @UseGuards(JwtAuthGuard)
  @Put('growth-records/:id')
  async updateGrowthRecord(
    @Request() req: any,
    @Param('id') recordId: string,
    @Body() body: UpdateGrowthRecordDto,
  ): Promise<GrowthRecordDto> {
    const userId = req.user.userId;
    return this.patientService.updateGrowthRecord(userId, recordId, body);
  }

  @UseGuards(JwtAuthGuard)
  @Delete('growth-records/:id')
  async deleteGrowthRecord(
    @Request() req: any,
    @Param('id') recordId: string,
  ): Promise<{ success: true }> {
    const userId = req.user.userId;
    await this.patientService.deleteGrowthRecord(userId, recordId);
    return { success: true };
  }

  @UseGuards(JwtAuthGuard)
  @Put('profile')
  async updateProfile(
    @Request() req: any,
    @Body() body: UpdatePatientProfileDto,
  ): Promise<PatientProfileDto> {
    const userId = req.user.userId;
    return this.patientService.updateProfile(userId, body);
  }

  @UseGuards(JwtAuthGuard)
  @Post('dietary')
  async updateDietary(
    @Request() req: any,
    @Body() body: { recommendation: string; allergy_warning: string; added_food?: string }
  ) {
    const userId = req.user.userId;
    return this.patientService.addDietaryRecord(userId, body);
  }
}
