export interface DoctorWorkbenchSessionDto {
  sessionId: string;
  patientUserId: string;
  patientBirthday: string;
  patientGender: number;
  knownAllergens: string;
  lastActiveAt: string;
  status: 'active' | 'followup' | 'closed';
  latestMessagePreview: string;
  latestMessageSender: 'user' | 'ai' | 'unknown';
}

export interface DoctorDietaryAlertDto {
  recordId: string;
  patientUserId: string;
  addedFood: string;
  allergyWarning: string;
  createdAt: string;
}

export interface DoctorWorkbenchDto {
  summary: {
    totalSessions: number;
    activePatients: number;
    dietaryAlerts: number;
  };
  sessions: DoctorWorkbenchSessionDto[];
  dietaryAlerts: DoctorDietaryAlertDto[];
}

export interface DoctorWorkbenchMessageDto {
  id: string;
  sender: 'user' | 'ai';
  content: string;
  createdAt: string;
}

export interface DoctorWorkbenchSessionDetailDto {
  sessionId: string;
  patientUserId: string;
  patientBirthday: string;
  patientGender: number;
  knownAllergens: string;
  medicalHistory: string;
  lastOcrSummary: string;
  lastActiveAt: string;
  status: 'active' | 'followup' | 'closed';
  doctorNote: string;
  messages: DoctorWorkbenchMessageDto[];
}

export interface UpdateDoctorSessionRequest {
  status: 'active' | 'followup' | 'closed';
  doctorNote: string;
}
