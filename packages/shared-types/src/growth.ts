export interface GrowthRecordDto {
  id: string;
  ageMonths: number;
  monthLabel: string;
  weight: number;
  height: number | null;
  createdAt: string;
}

export interface CreateGrowthRecordRequest {
  ageMonths: number;
  weight: number;
  height?: number | null;
}

export interface UpdateGrowthRecordRequest {
  ageMonths: number;
  weight: number;
  height?: number | null;
}
