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
