export interface Citation {
  title: string;
  chapter?: string;
  content: string;
  sourceType?: 'guideline' | 'safety_rule' | 'model_inference';
}

export interface EvidenceLayer {
  sourceType: 'guideline' | 'safety_rule' | 'model_inference';
  title: string;
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
  question?: string;
  options?: string[];
  hours_passed?: number;
  nextDate?: string;
  tasks?: string[];
}

export interface AssessmentPayload {
  triageLevel: 'home_observation' | 'visit_within_24h' | 'clinic_soon' | 'emergency_now';
  triageReason: string;
  trendDirection?: 'worsening' | 'improving' | 'fluctuating' | 'stable' | 'unknown';
  trendReason?: string;
  recommendedActions: string[];
  warningSignals: string[];
  constraintWarnings: string[];
  ageBand?: string;
  symptomCategory?: 'fever' | 'cough' | 'gastro' | 'rash' | 'general';
  summaryText?: string;
  evidenceLayers?: EvidenceLayer[];
}

export type MessagePayload =
  | DietaryFormPayload
  | OcrResultPayload
  | FollowupPayload
  | AssessmentPayload;

export interface Message {
  id: number;
  text: string;
  sender: 'user' | 'ai';
  isError?: boolean;
  type?: 'text' | 'dietary_form' | 'ocr_result' | 'followup_card' | 'assessment_card';
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
