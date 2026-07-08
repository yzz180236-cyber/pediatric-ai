export type AuthSource = 'dev' | 'wechat' | 'web';

export interface PatientProfileDto {
  id: string;
  userId: string;
  displayName: string;
  birthday: string;
  gender: number;
  knownAllergens: string;
  medicalHistory: string;
  lastOcrSummary: string;
}

export interface UpdatePatientProfileRequest {
  displayName: string;
  birthday: string;
  gender: number;
  knownAllergens: string;
}
