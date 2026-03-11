import { supabase } from './supabase';
import { Config } from '@/constants/config';
import type {
  Profile,
  ProfileCreate,
  ProfileUpdate,
  PaginatedResponse,
  DiagnosisSession,
  DiagnosisTurnResponse,
  Report,
  ChatConversation,
  ChatConversationDetail,
  ChatTurnResponse,
} from '@/types/api';
import type { Attachment } from '@/hooks/useAttachMenu';
import type { StreamEvent } from '@/types/api';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error('Not authenticated');
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

function extractErrorMessage(error: Record<string, unknown>, status: number): string {
  const detail = error.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ');
  }
  return `HTTP ${status}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${Config.apiUrl}${path}`, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(extractErrorMessage(error, response.status));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// ── Profiles ──────────────────────────────────────────────────────────────────

export const profilesApi = {
  list: (page = 1, size = 50) =>
    request<PaginatedResponse<Profile>>(`/profiles?page=${page}&size=${size}`),
  get: (pid: string) =>
    request<Profile>(`/profiles/${pid}`),
  create: (body: ProfileCreate) =>
    request<Profile>('/profiles', { method: 'POST', body: JSON.stringify(body) }),
  update: (pid: string, body: ProfileUpdate) =>
    request<Profile>(`/profiles/${pid}`, { method: 'PATCH', body: JSON.stringify(body) }),
  remove: (pid: string) =>
    request<void>(`/profiles/${pid}`, { method: 'DELETE' }),
};

// ── Diagnosis ─────────────────────────────────────────────────────────────────

export const diagnosisApi = {
  list: (pid: string, page = 1) =>
    request<PaginatedResponse<DiagnosisSession>>(`/profiles/${pid}/diagnosis?page=${page}`),
  get: (pid: string, sid: string) =>
    request<DiagnosisSession>(`/profiles/${pid}/diagnosis/${sid}`),
  create: (pid: string, chief_complaint: string) =>
    request<DiagnosisSession>(`/profiles/${pid}/diagnosis`, {
      method: 'POST',
      body: JSON.stringify({ chief_complaint }),
    }),
  /** Lightweight create — just the session record, no LLM call. */
  createOnly: (pid: string, chief_complaint: string) =>
    request<DiagnosisSession>(`/profiles/${pid}/diagnosis/create`, {
      method: 'POST',
      body: JSON.stringify({ chief_complaint }),
    }),
  sendMessage: (pid: string, sid: string, content: string, files?: Attachment[]) =>
    multipartRequest<DiagnosisTurnResponse>(
      `/profiles/${pid}/diagnosis/${sid}/messages`,
      { content },
      files,
    ),
  updateStatus: (pid: string, sid: string, status: 'closed' | 'resolved' | 'abandoned') =>
    request<DiagnosisSession>(`/profiles/${pid}/diagnosis/${sid}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  delete: (pid: string, sid: string) =>
    request<void>(`/profiles/${pid}/diagnosis/${sid}`, { method: 'DELETE' }),
  rename: (pid: string, sid: string, title: string) =>
    request<DiagnosisSession>(`/profiles/${pid}/diagnosis/${sid}/rename`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
};

// ── Reports ───────────────────────────────────────────────────────────────────

export const reportsApi = {
  list: (pid: string, page = 1) =>
    request<PaginatedResponse<Report>>(`/profiles/${pid}/reports?page=${page}`),
  get: (pid: string, rid: string) =>
    request<Report>(`/profiles/${pid}/reports/${rid}`),
  upload: async (pid: string, file: { uri: string; name: string; type: string }) => {
    const headers = await getAuthHeaders();
    const formData = new FormData();
    formData.append('file', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
    const response = await fetch(`${Config.apiUrl}/profiles/${pid}/reports/upload`, {
      method: 'POST',
      headers: { Authorization: headers.Authorization ?? '' },
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(extractErrorMessage(error, response.status));
    }
    return response.json() as Promise<Report>;
  },
  reanalyze: (pid: string, rid: string) =>
    request<Report>(`/profiles/${pid}/reports/${rid}/reanalyze`, { method: 'POST' }),
};

// ── Multipart helper ─────────────────────────────────────────────────────────

async function multipartRequest<T>(
  path: string,
  fields: Record<string, string>,
  files: Attachment[] = [],
): Promise<T> {
  const headers = await getAuthHeaders();
  const formData = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    formData.append(key, value);
  }
  for (const f of files) {
    formData.append('files', { uri: f.uri, name: f.name, type: f.type } as unknown as Blob);
  }
  const response = await fetch(`${Config.apiUrl}${path}`, {
    method: 'POST',
    headers: { Authorization: headers.Authorization ?? '' },
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(extractErrorMessage(error, response.status));
  }
  return response.json() as Promise<T>;
}

// ── SSE Streaming helper ────────────────────────────────────────────────────

type DoneEvent = Extract<StreamEvent, { type: 'done' }>;

export interface StreamHandle {
  promise: Promise<DoneEvent>;
  abort: () => void;
}

function streamMultipartRequest(
  path: string,
  fields: Record<string, string>,
  files: Attachment[] = [],
  onEvent: (event: StreamEvent) => void,
): StreamHandle {
  let xhr: XMLHttpRequest | null = null;
  let aborted = false;

  const promise = (async () => {
    const headers = await getAuthHeaders();
    if (aborted) throw new Error('Stream aborted');

    const formData = new FormData();
    for (const [key, value] of Object.entries(fields)) {
      formData.append(key, value);
    }
    for (const f of files) {
      formData.append('files', { uri: f.uri, name: f.name, type: f.type } as unknown as Blob);
    }

    return new Promise<DoneEvent>((resolve, reject) => {
      xhr = new XMLHttpRequest();
      xhr.open('POST', `${Config.apiUrl}${path}`);
      xhr.setRequestHeader('Authorization', headers.Authorization ?? '');
      xhr.responseType = 'text';

      let cursor = 0;
      let resolved = false;

      xhr.onreadystatechange = () => {
        if (xhr!.readyState >= 3 && xhr!.status === 200) {
          const newText = xhr!.responseText.substring(cursor);
          cursor = xhr!.responseText.length;

          for (const line of newText.split('\n')) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(trimmed.substring(6)) as StreamEvent;
              onEvent(event);
              if (event.type === 'done' && !resolved) {
                resolved = true;
                resolve(event);
              } else if (event.type === 'error' && !resolved) {
                resolved = true;
                const msg = (event as { message?: string }).message || 'Processing failed';
                reject(new Error(msg));
              }
            } catch {
              // Incomplete JSON in this chunk — will arrive in next onreadystatechange
            }
          }
        }
      };

      xhr.onload = () => {
        if (!resolved) {
          let detail: string;
          if (xhr!.status !== 200) {
            detail = `HTTP ${xhr!.status}`;
            try {
              const body = JSON.parse(xhr!.responseText);
              detail = body.detail || detail;
            } catch { /* ignore parse failure */ }
          } else {
            detail = 'Connection closed unexpectedly. Please try again.';
          }
          reject(new Error(detail));
        }
      };
      xhr.onerror = () => {
        if (!resolved) reject(new Error('Stream connection failed'));
      };
      xhr.onabort = () => {
        if (!resolved) reject(new Error('Stream aborted'));
      };
      xhr.send(formData);
    });
  })();

  return {
    promise,
    abort: () => {
      aborted = true;
      xhr?.abort();
    },
  };
}

// ── Chat ─────────────────────────────────────────────────────────────────────

export const chatApi = {
  list: (pid: string, page = 1) =>
    request<PaginatedResponse<ChatConversation>>(`/profiles/${pid}/chat?page=${page}`),
  get: (pid: string, cid: string) =>
    request<ChatConversationDetail>(`/profiles/${pid}/chat/${cid}`),
  rename: (pid: string, cid: string, topic: string) =>
    request<ChatConversation>(`/profiles/${pid}/chat/${cid}`, {
      method: 'PATCH',
      body: JSON.stringify({ topic }),
    }),
  delete: (pid: string, cid: string) =>
    request<void>(`/profiles/${pid}/chat/${cid}`, { method: 'DELETE' }),
  send: (pid: string, content: string, conversation_id?: string, topic?: string, files?: Attachment[]) => {
    const fields: Record<string, string> = { content };
    if (conversation_id) fields.conversation_id = conversation_id;
    if (topic) fields.topic = topic;
    return multipartRequest<ChatTurnResponse>(`/profiles/${pid}/chat`, fields, files);
  },
  sendStream: (
    pid: string,
    content: string,
    onEvent: (event: StreamEvent) => void,
    conversationId?: string,
    topic?: string,
    files?: Attachment[],
  ) => {
    const fields: Record<string, string> = { content };
    if (conversationId) fields.conversation_id = conversationId;
    if (topic) fields.topic = topic;
    return streamMultipartRequest(`/profiles/${pid}/chat/stream`, fields, files, onEvent);
  },
};

// ── Diagnosis streaming ──────────────────────────────────────────────────────

export const diagnosisStreamApi = {
  sendMessage: (
    pid: string,
    content: string,
    onEvent: (event: StreamEvent) => void,
    sessionId?: string,
    chiefComplaint?: string,
    files?: Attachment[],
    structuredResponse?: Record<string, unknown>,
  ) => {
    const fields: Record<string, string> = { content };
    if (sessionId) fields.session_id = sessionId;
    if (chiefComplaint) fields.chief_complaint = chiefComplaint;
    if (structuredResponse) fields.structured_response = JSON.stringify(structuredResponse);
    return streamMultipartRequest(
      `/profiles/${pid}/diagnosis/stream`,
      fields,
      files,
      onEvent,
    );
  },
};
