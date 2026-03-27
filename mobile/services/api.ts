import { supabase } from './supabase';
import { logger } from './logger';
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
  // slowapi returns { "error": "Rate limit exceeded: ..." }
  if (typeof error.error === 'string') return error.error;
  return `HTTP ${status}`;
}

/** Thrown when the server returns HTTP 429. */
export class RateLimitError extends Error {
  /** Seconds until the client can retry, from the Retry-After header. */
  retryAfter: number | undefined;
  constructor(message: string, retryAfter?: number) {
    super(message);
    this.name = 'RateLimitError';
    this.retryAfter = retryAfter;
  }
}

// Coalesce concurrent token refresh attempts into a single promise
let refreshPromise: Promise<void> | null = null;

async function request<T>(path: string, options: RequestInit = {}, _isRetry = false): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase();
  const start = Date.now();
  let status = 0;
  try {
    const headers = await getAuthHeaders();
    const response = await fetch(`${Config.apiUrl}${path}`, {
      ...options,
      headers: { ...headers, ...options.headers },
    });
    status = response.status;
    const rid = response.headers.get('x-request-id') ?? undefined;
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      const msg = extractErrorMessage(error, response.status);
      logger.error('api', `${method} ${path} ${status}`, { duration_ms: Date.now() - start, rid, error: msg });

      // 401 retry: refresh token once, then retry the request
      if (response.status === 401 && !_isRetry) {
        logger.info('api', '401 received — attempting token refresh');
        if (!refreshPromise) {
          refreshPromise = supabase.auth.refreshSession()
            .then(({ error }) => {
              if (error) throw error;
            })
            .finally(() => { refreshPromise = null; });
        }
        try {
          await refreshPromise;
        } catch {
          // Refresh failed — sign out immediately
          logger.warn('api', 'Token refresh failed — signing out');
          await supabase.auth.signOut();
          throw new Error(msg);
        }
        return request<T>(path, options, true);
      }

      // 401 after retry: session is truly expired — sign out
      if (response.status === 401 && _isRetry) {
        logger.warn('api', '401 after refresh — signing out');
        await supabase.auth.signOut();
        throw new Error(msg);
      }

      if (response.status === 429) {
        const retryAfter = parseInt(response.headers.get('Retry-After') ?? '', 10) || undefined;
        throw new RateLimitError(msg, retryAfter);
      }
      throw new Error(msg);
    }
    logger.info('api', `${method} ${path} ${status}`, { duration_ms: Date.now() - start, rid });
    // Flush any queued client logs on successful request
    logger.flushPending();
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  } catch (err) {
    if (status === 0) {
      // Network error — fetch itself threw (no response)
      const msg = err instanceof Error ? err.message : 'Unknown error';
      logger.error('api', `${method} ${path} NETWORK_ERROR`, { duration_ms: Date.now() - start, error: msg });
    }
    throw err;
  }
}

// ── Account ───────────────────────────────────────────────────────────────────

export const accountApi = {
  delete: () => request<void>('/auth/account', { method: 'DELETE' }),
};

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
  const start = Date.now();
  let status = 0;
  try {
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
    status = response.status;
    const rid = response.headers.get('x-request-id') ?? undefined;
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      const msg = extractErrorMessage(error, response.status);
      logger.error('api', `POST ${path} ${status}`, { duration_ms: Date.now() - start, rid, error: msg });
      throw new Error(msg);
    }
    logger.info('api', `POST ${path} ${status}`, { duration_ms: Date.now() - start, rid });
    return response.json() as Promise<T>;
  } catch (err) {
    if (status === 0) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      logger.error('api', `POST ${path} NETWORK_ERROR`, { duration_ms: Date.now() - start, error: msg });
    }
    throw err;
  }
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

    const streamStart = Date.now();
    let eventsReceived = 0;
    let lastEventType = '';
    let rid: string | undefined;

    logger.info('stream', `OPEN ${path}`, { fields: Object.keys(fields) });

    return new Promise<DoneEvent>((resolve, reject) => {
      xhr = new XMLHttpRequest();
      xhr.open('POST', `${Config.apiUrl}${path}`);
      xhr.setRequestHeader('Authorization', headers.Authorization ?? '');
      xhr.responseType = 'text';

      let cursor = 0;
      let resolved = false;

      xhr.onreadystatechange = () => {
        // Capture request ID from response headers as soon as headers arrive
        if (xhr!.readyState >= 2 && !rid) {
          try {
            rid = xhr!.getResponseHeader('x-request-id') ?? undefined;
          } catch { /* headers not ready yet */ }
        }

        if (xhr!.readyState >= 3 && xhr!.status === 200) {
          const newText = xhr!.responseText.substring(cursor);
          cursor = xhr!.responseText.length;

          for (const line of newText.split('\n')) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(trimmed.substring(6)) as StreamEvent;
              eventsReceived++;
              lastEventType = event.type;
              onEvent(event);
              if (event.type === 'done' && !resolved) {
                resolved = true;
                logger.info('stream', `DONE ${path}`, {
                  duration_ms: Date.now() - streamStart,
                  events: eventsReceived,
                  rid,
                });
                // Flush any queued error logs from previous failed attempts
                logger.flushPending();
                resolve(event);
              } else if (event.type === 'error' && !resolved) {
                resolved = true;
                const msg = (event as { message?: string }).message || 'Processing failed';
                logger.error('stream', `SERVER_ERROR ${path}`, {
                  duration_ms: Date.now() - streamStart,
                  events: eventsReceived,
                  rid,
                  error: msg,
                });
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
          const status = xhr!.status;
          if (status === 200) {
            // Connection was working (200) but closed before DONE event —
            // same as onerror with status 200 (iOS backgrounding).
            logger.error('stream', `INTERRUPTED ${path}`, {
              duration_ms: Date.now() - streamStart,
              status,
              events: eventsReceived,
              last_event: lastEventType || null,
              rid,
            });
            reject(new Error('Stream interrupted'));
          } else {
            let detail = `HTTP ${status}`;
            try {
              const body = JSON.parse(xhr!.responseText);
              detail = body.detail || body.error || detail;
            } catch { /* ignore parse failure */ }
            logger.error('stream', `CLOSED ${path}`, {
              duration_ms: Date.now() - streamStart,
              status,
              events: eventsReceived,
              last_event: lastEventType || null,
              rid,
              error: detail,
            });
            if (status === 429) {
              const retryAfter = parseInt(xhr!.getResponseHeader('Retry-After') ?? '', 10) || undefined;
              reject(new RateLimitError(detail, retryAfter));
            } else {
              reject(new Error(detail));
            }
          }
        }
      };
      xhr.onerror = () => {
        if (!resolved) {
          // xhr.status === 200 means the connection was established and working,
          // then got killed (iOS backgrounding). status === 0 means a real
          // network failure (never connected or DNS failure).
          const wasConnected = xhr!.status === 200;
          logger.error('stream', `${wasConnected ? 'INTERRUPTED' : 'NETWORK_ERROR'} ${path}`, {
            duration_ms: Date.now() - streamStart,
            xhr_status: xhr!.status,
            xhr_state: xhr!.readyState,
            events: eventsReceived,
            last_event: lastEventType || null,
            rid,
          });
          reject(new Error(wasConnected ? 'Stream interrupted' : 'Stream connection failed'));
        }
      };
      xhr.onabort = () => {
        if (!resolved) {
          logger.warn('stream', `ABORTED ${path}`, {
            duration_ms: Date.now() - streamStart,
            events: eventsReceived,
            last_event: lastEventType || null,
            rid,
          });
          reject(new Error('Stream aborted'));
        }
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
