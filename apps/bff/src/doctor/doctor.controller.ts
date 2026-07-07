import { Body, Controller, Get, Param, Put, Req, UnauthorizedException, UseGuards } from '@nestjs/common';
import { DoctorWorkbenchDto, DoctorWorkbenchSessionDetailDto, UpdateDoctorSessionRequest } from '@pediatric-ai/shared-types';
import { JwtAuthGuard } from '../common/guards/jwt-auth.guard';
import { DoctorService } from './doctor.service';

class UpdateDoctorSessionDto implements UpdateDoctorSessionRequest {
  status: 'active' | 'followup' | 'closed';
  doctorNote: string;
}

@Controller('doctor')
@UseGuards(JwtAuthGuard)
export class DoctorController {
  constructor(private readonly doctorService: DoctorService) {}

  @Get('workbench')
  async getWorkbench(@Req() req: Request): Promise<DoctorWorkbenchDto> {
    const role = (req as any).user?.role;
    if (role !== 'doctor') {
      throw new UnauthorizedException('无权访问医生工作台');
    }
    return this.doctorService.getWorkbench();
  }

  @Get('workbench/sessions/:id')
  async getSessionDetail(
    @Param('id') sessionId: string,
    @Req() req: Request,
  ): Promise<DoctorWorkbenchSessionDetailDto> {
    const role = (req as any).user?.role;
    if (role !== 'doctor') {
      throw new UnauthorizedException('无权访问医生工作台');
    }
    return this.doctorService.getSessionDetail(sessionId);
  }

  @Put('workbench/sessions/:id')
  async updateSessionDetail(
    @Param('id') sessionId: string,
    @Body() body: UpdateDoctorSessionDto,
    @Req() req: Request,
  ): Promise<DoctorWorkbenchSessionDetailDto> {
    const role = (req as any).user?.role;
    if (role !== 'doctor') {
      throw new UnauthorizedException('无权访问医生工作台');
    }
    return this.doctorService.updateSession(sessionId, body);
  }
}
