import axios, { AxiosError } from 'axios';
import type {
  ChatResponse,
  Document,
  HealthStatus,
  Question,
  Subject,
  SummaryResponse,
} from '../types';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:5000/api';
export const MAX_UPLOAD_MB = 50;

const client = axios.create({ baseURL: API_BASE_URL, timeout: 120_000 });

/** Extrae el mensaje de error del backend ({success:false, error}) o uno genérico. */
export function getErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const data = err.response?.data as { error?: string } | undefined;
    if (data?.error) return data.error;
    if (err.code === 'ECONNABORTED') return 'La solicitud tardó demasiado';
    if (!err.response) return 'No se pudo conectar con el servidor';
    return `Error ${err.response.status}`;
  }
  return err instanceof Error ? err.message : 'Error desconocido';
}

// --- Materias ---------------------------------------------------------------

export async function getSubjects(): Promise<Subject[]> {
  const { data } = await client.get('/subjects');
  return data.subjects;
}

export async function createSubject(name: string): Promise<Subject> {
  const { data } = await client.post('/subjects', { name });
  return data.subject;
}

export async function renameSubject(id: number, name: string): Promise<Subject> {
  const { data } = await client.patch(`/subjects/${id}`, { name });
  return data.subject;
}

export async function deleteSubject(id: number): Promise<void> {
  await client.delete(`/subjects/${id}`);
}

// --- Documentos -------------------------------------------------------------

export async function uploadDocument(
  file: File,
  subjectId?: number,
  onProgress?: (percent: number) => void,
): Promise<Document> {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    throw new Error('Solo se aceptan PDFs');
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    throw new Error(`El archivo supera ${MAX_UPLOAD_MB}MB`);
  }
  const form = new FormData();
  form.append('file', file);
  if (subjectId !== undefined) form.append('subject_id', String(subjectId));
  const { data } = await client.post('/documents/upload', form, {
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
    },
  });
  return {
    id: data.document_id,
    subject_id: data.subject_id,
    filename: data.filename,
    status: data.status,
    upload_date: new Date().toISOString(),
    chunks_count: null,
  };
}

export async function getDocuments(subjectId?: number): Promise<Document[]> {
  const { data } = await client.get('/documents', { params: subjectId ? { subject_id: subjectId } : {} });
  return data.documents;
}

export async function deleteDocument(id: number): Promise<void> {
  await client.delete(`/documents/${id}`);
}

export async function startSummary(documentId: number): Promise<void> {
  await client.post(`/documents/${documentId}/summary`);
}

export async function getSummary(documentId: number): Promise<SummaryResponse> {
  const { data } = await client.get<SummaryResponse>(`/documents/${documentId}/summary`);
  return data;
}

// --- Chat y estudio ---------------------------------------------------------

export interface Scope {
  subjectId?: number;
  documentId?: number;
}

export async function sendMessage(
  message: string,
  conversationId?: number,
  scope: Scope = {},
  topK = 5,
): Promise<ChatResponse> {
  const { data } = await client.post<ChatResponse>('/chat', {
    message,
    conversation_id: conversationId ?? null,
    top_k: topK,
    subject_id: scope.subjectId ?? null,
    document_id: scope.documentId ?? null,
  });
  return data;
}

export async function generateQuestions(count: number, scope: Scope, topic?: string): Promise<Question[]> {
  const { data } = await client.post(
    '/study/questions',
    {
      count,
      topic: topic || null,
      subject_id: scope.subjectId ?? null,
      document_id: scope.documentId ?? null,
    },
    { timeout: 300_000 },
  );
  return data.questions;
}

export async function getHealth(): Promise<HealthStatus> {
  const { data } = await client.get<HealthStatus>('/health', { timeout: 10_000 });
  return data;
}
