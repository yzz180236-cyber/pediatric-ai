export interface GrowthRecordDto {
  id: string;
  ageMonths: number;
  monthLabel: string;
  weight: number;
  createdAt: string;
}

export interface CreateGrowthRecordRequest {
  ageMonths: number;
  weight: number;
}

export interface UpdateGrowthRecordRequest {
  ageMonths: number;
  weight: number;
}
