export interface Citation {
  title: string;
  chapter?: string;
  content: string;
}

export interface DietaryFormPayload {
  ageRange: string;
  recommendations: string[];
}

export interface OcrResultPayload {
  rawText: string;
  abnormalItems: string[];
}

export interface FollowupPayload {
  nextDate: string;
  tasks: string[];
}

export type MessagePayload = DietaryFormPayload | OcrResultPayload | FollowupPayload;

export interface Message {
  id: number;
  text: string;
  sender: 'user' | 'ai';
  isError?: boolean;
  type?: 'text' | 'dietary_form' | 'ocr_result' | 'followup_card';
  payload?: MessagePayload;
  citations?: Citation[];
  imageUrl?: string;
  thoughts?: string[];
  duration?: number;
}

export interface GrowthRecord {
  month: string;
  weight: number;
  height?: number;
}
