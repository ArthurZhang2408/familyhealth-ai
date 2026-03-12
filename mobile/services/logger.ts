/**
 * Client-side structured logger.
 *
 * Captures API requests, stream lifecycle, and errors in a ring buffer.
 * Logs can be viewed via the debug screen or reported to the backend.
 *
 * Usage:
 *   logger.info('api', 'Request completed', { path, status, duration_ms });
 *   logger.error('stream', 'Connection failed', { path, error });
 *   logger.getEntries()  // recent logs
 *   logger.dump()        // full text dump for sharing
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';
export type LogCategory = 'api' | 'stream' | 'auth' | 'nav' | 'app';

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  category: LogCategory;
  message: string;
  data?: Record<string, unknown>;
}

const MAX_ENTRIES = 500;
const entries: LogEntry[] = [];
/** Entries queued for server reporting (failed to send earlier). */
let pendingReport: LogEntry[] = [];

function log(level: LogLevel, category: LogCategory, message: string, data?: Record<string, unknown>) {
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    category,
    message,
    data,
  };
  entries.push(entry);
  if (entries.length > MAX_ENTRIES) {
    entries.splice(0, entries.length - MAX_ENTRIES);
  }

  // Also emit to console in dev for visibility
  if (__DEV__) {
    const prefix = `[${category}]`;
    const fn = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
    fn(prefix, message, data ?? '');
  }
}

export const logger = {
  debug: (category: LogCategory, message: string, data?: Record<string, unknown>) =>
    log('debug', category, message, data),
  info: (category: LogCategory, message: string, data?: Record<string, unknown>) =>
    log('info', category, message, data),
  warn: (category: LogCategory, message: string, data?: Record<string, unknown>) =>
    log('warn', category, message, data),
  error: (category: LogCategory, message: string, data?: Record<string, unknown>) =>
    log('error', category, message, data),

  /** Get all log entries (newest last). */
  getEntries: (): readonly LogEntry[] => entries,

  /** Get entries filtered by level and/or category. */
  filter: (opts: { level?: LogLevel; category?: LogCategory; last?: number }): LogEntry[] => {
    let result = entries;
    if (opts.level) result = result.filter((e) => e.level === opts.level);
    if (opts.category) result = result.filter((e) => e.category === opts.category);
    if (opts.last) result = result.slice(-opts.last);
    return result;
  },

  /** Full text dump — suitable for copy/paste or sharing. */
  dump: (): string =>
    entries
      .map((e) => {
        const dataStr = e.data ? ' ' + JSON.stringify(e.data) : '';
        return `${e.timestamp} ${e.level.toUpperCase()} [${e.category}] ${e.message}${dataStr}`;
      })
      .join('\n'),

  /** Clear all entries. */
  clear: () => {
    entries.length = 0;
  },

  /**
   * Report recent error/warn logs to the backend for server-side correlation.
   * If the server is unreachable, queues entries for delivery on the next
   * successful call to {@link flushPending}.
   */
  reportToServer: async (opts?: { last?: number; minLevel?: LogLevel }) => {
    const levels: LogLevel[] = ['error', 'warn'];
    if (opts?.minLevel === 'info') levels.push('info');

    const toSend = entries
      .filter((e) => levels.includes(e.level))
      .slice(-(opts?.last ?? 50));

    if (toSend.length === 0) return;

    const ok = await _sendToServer(toSend);
    if (!ok) {
      // Queue for later delivery
      pendingReport = [...pendingReport, ...toSend].slice(-MAX_ENTRIES);
    }
  },

  /**
   * Flush any queued log entries that failed to send earlier.
   * Call this after a successful API request to piggyback on the
   * recovered connection. No-op if nothing is queued.
   */
  flushPending: async () => {
    if (pendingReport.length === 0) return;
    const batch = pendingReport;
    pendingReport = [];
    const ok = await _sendToServer(batch);
    if (!ok) {
      // Still unreachable — re-queue
      pendingReport = [...batch, ...pendingReport].slice(-MAX_ENTRIES);
    }
  },
};

async function _sendToServer(toSend: LogEntry[]): Promise<boolean> {
  try {
    const { Config: C } = await import('@/constants/config');
    const { supabase: sb } = await import('./supabase');
    const { data } = await sb.auth.getSession();
    const token = data.session?.access_token;
    if (!token) return false;

    const res = await fetch(`${C.apiUrl}/debug/client-logs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(toSend),
    });
    return res.ok;
  } catch {
    return false;
  }
}
