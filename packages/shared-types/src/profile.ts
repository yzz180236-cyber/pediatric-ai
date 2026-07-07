export type AuthSource = 'dev' | 'wechat' | 'web';

export interface PatientProfileDto {
  id: string;
  userId: string;
  birthday: string;
  gender: number;
  knownAllergens: string;
  medicalHistory: string;
  lastOcrSummary: string;
}

export interface UpdatePatientProfileRequest {
  birthday: string;
  gender: number;
  knownAllergens: string;
}
