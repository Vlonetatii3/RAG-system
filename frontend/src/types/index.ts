export type DocumentStatus = 'processing' | 'completed' | 'failed';
export type SummaryStatus = 'processing' | 'completed' | 'failed' | null;

export interface Subject {
  id: number;
  name: string;
  created_at: string;
  documents_count: number;
}

export interface Document {
  id: number;
  subject_id?: number;
  filename: string;
  upload_date: string;
  status: DocumentStatus;
  chunks_count?: number | null;
  error?: string | null;
  page_count?: number | null;
  pages_without_text?: number;
  summary_status?: SummaryStatus;
  summary_progress?: string | null;
  summary_error?: string | null;
}

export interface Source {
  document_id: number;
  chunk_id: number;
  filename?: string;
  page_start?: number | null;
  page_end?: number | null;
  text: string;
  similarity: number;
}

export interface Message {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  createdAt: string;
  processingTimeMs?: number;
  isError?: boolean;
}

export interface ChatResponse {
  success: boolean;
  conversation_id: number;
  reply: string;
  sources: Source[];
  processing_time_ms: number;
}

export interface SummaryResponse {
  document_id: number;
  filename: string;
  summary_status: SummaryStatus;
  summary_progress: string | null;
  summary_error: string | null;
  summary: string | null;
}

export interface Question {
  question: string;
  answer: string;
  source: string | null;
  document_id: number | null;
}

export interface HealthStatus {
  status: 'healthy' | 'unhealthy';
  database: string;
  ollama: string;
  model: string;
  model_available?: boolean;
  embeddings_model?: string;
  embeddings_model_available?: boolean;
  timestamp?: string;
}

export interface Toast {
  id: number;
  type: 'error' | 'success' | 'info';
  text: string;
}
