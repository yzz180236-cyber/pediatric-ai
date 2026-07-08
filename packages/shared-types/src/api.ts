export interface BaseResponse<T> {
  code: number;
  message: string;
  data?: T;
}

export interface ChatRequest {
  message: string;
  sessionId?: string;
}

export interface CitationDto {
  title: string;
  chapter?: string;
  content: string;
}

export interface ChatResponse {
  reply: string;
  sourceNodes?: CitationDto[];
}

export interface ChatSessionActionRequest {
  action: 'mark_followup' | 'request_doctor_review';
}

export interface ChatSessionActionResponse {
  sessionId: string;
  status: 'active' | 'followup' | 'closed';
  doctorNote: string;
}
