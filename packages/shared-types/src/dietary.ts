export interface DietaryRecordDto {
  id: string;
  recommendation: string;
  allergyWarning: string;
  addedFood: string;
  createdAt: string;
}

export interface UpdateDietaryRecordRequest {
  recommendation: string;
  allergyWarning: string;
  addedFood: string;
}
