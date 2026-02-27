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

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${Config.apiUrl}${path}`, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail ?? `HTTP ${response.status}`);
  }
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
  sendMessage: (pid: string, sid: string, content: string) =>
    request<DiagnosisTurnResponse>(`/profiles/${pid}/diagnosis/${sid}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  updateStatus: (pid: string, sid: string, status: 'closed' | 'resolved' | 'abandoned') =>
    request<DiagnosisSession>(`/profiles/${pid}/diagnosis/${sid}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
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
      throw new Error(error.detail ?? `HTTP ${response.status}`);
    }
    return response.json() as Promise<Report>;
  },
  reanalyze: (pid: string, rid: string) =>
    request<Report>(`/profiles/${pid}/reports/${rid}/reanalyze`, { method: 'POST' }),
};

// ── Chat ─────────────────────────────────────────────────────────────────────

export const chatApi = {
  list: (pid: string, page = 1) =>
    request<PaginatedResponse<ChatConversation>>(`/profiles/${pid}/chat?page=${page}`),
  get: (pid: string, cid: string) =>
    request<ChatConversationDetail>(`/profiles/${pid}/chat/${cid}`),
  send: (pid: string, content: string, conversation_id?: string, topic?: string) =>
    request<ChatTurnResponse>(`/profiles/${pid}/chat`, {
      method: 'POST',
      body: JSON.stringify({ content, conversation_id, topic }),
    }),
};
