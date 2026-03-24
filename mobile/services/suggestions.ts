import type { IconName } from '@/components/Icon';

export type SuggestionAccent = 'warning' | 'success' | 'primary' | 'default';

export interface Suggestion {
  id: string;
  type: 'continue' | 'follow_up' | 'condition' | 'medication' | 'generic';
  text: string;
  icon: IconName;
  accent: SuggestionAccent;
  sessionId?: string;
  sessionType?: 'chat' | 'diagnosis';
}

const cache = new Map<string, Suggestion[]>();

export function getCachedSuggestions(key: string): Suggestion[] | undefined {
  return cache.get(key);
}

export function setCachedSuggestions(key: string, suggestions: Suggestion[]): void {
  cache.set(key, suggestions);
}

export function cacheKey(pid: string, mode: string): string {
  return `${pid}-${mode}`;
}

const MAX_SUGGESTIONS = 6;

type PoolEntry = Omit<Suggestion, 'id'> & { needs?: 'medications' | 'conditions' | 'allergies' };

const CHAT_POOL: PoolEntry[] = [
  { type: 'generic', text: 'Review my medications', icon: 'medkit', accent: 'default', needs: 'medications' },
  { type: 'generic', text: 'Explain a lab result', icon: 'flask', accent: 'default' },
  { type: 'generic', text: 'Prevention & vaccines', icon: 'shield', accent: 'default' },
  { type: 'generic', text: 'Sleep & stress tips', icon: 'brain', accent: 'default' },
  { type: 'generic', text: 'Heart health basics', icon: 'heart-clipboard', accent: 'default' },
  { type: 'generic', text: 'When should I see a doctor?', icon: 'doc-search', accent: 'default' },
  { type: 'generic', text: 'Common drug interactions', icon: 'medkit', accent: 'default', needs: 'medications' },
  { type: 'generic', text: 'Managing daily stress', icon: 'brain', accent: 'default' },
  { type: 'generic', text: 'Understanding blood work', icon: 'flask', accent: 'default' },
  { type: 'generic', text: 'Nutrition and diet basics', icon: 'shield', accent: 'default' },
  { type: 'generic', text: 'Exercise and recovery', icon: 'heart-clipboard', accent: 'default' },
  { type: 'generic', text: 'Allergy management', icon: 'alert-circle', accent: 'default', needs: 'allergies' },
];

const DIAGNOSIS_POOL: PoolEntry[] = [
  { type: 'generic', text: 'Sore throat and fever', icon: 'stethoscope', accent: 'default' },
  { type: 'generic', text: 'Stomach pain after eating', icon: 'alert-circle', accent: 'default' },
  { type: 'generic', text: 'Feeling short of breath', icon: 'heart-clipboard', accent: 'default' },
  { type: 'generic', text: 'Headache for several days', icon: 'doc-search', accent: 'default' },
  { type: 'generic', text: 'Persistent cough', icon: 'stethoscope', accent: 'default' },
  { type: 'generic', text: 'Lower back pain', icon: 'alert-circle', accent: 'default' },
  { type: 'generic', text: 'Skin rash or irritation', icon: 'medkit', accent: 'default' },
  { type: 'generic', text: 'Dizziness or lightheadedness', icon: 'brain', accent: 'default' },
  { type: 'generic', text: 'Joint pain and stiffness', icon: 'alert-circle', accent: 'default' },
  { type: 'generic', text: 'Trouble sleeping', icon: 'brain', accent: 'default' },
];

function isWithinDays(dateStr: string, days: number): boolean {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  return diff <= days * 24 * 60 * 60 * 1000;
}

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function buildSuggestions(
  mode: 'chat' | 'diagnosis',
  profile: { name: string; relationship: string; medical_conditions?: { name: string }[]; medications?: { name: string }[]; allergies?: { name: string }[] } | null,
  chatSessions: { id: string; topic?: string; updated_at: string }[],
  diagnosisSessions: { id: string; chief_complaint: string; title?: string; status: string; diagnosis_state?: { phase: string }; updated_at: string }[],
): Suggestion[] {
  const result: Suggestion[] = [];
  const isSelf = profile?.relationship === 'self';
  const pName = profile?.name ?? '';
  const hasMeds = (profile?.medications?.length ?? 0) > 0;
  const hasConds = (profile?.medical_conditions?.length ?? 0) > 0;
  const hasAllergies = (profile?.allergies?.length ?? 0) > 0;

  // 1. Incomplete diagnosis sessions (max 2)
  const incomplete = diagnosisSessions
    .filter((s) => s.status === 'active' && s.diagnosis_state?.phase !== 'complete')
    .slice(0, 2);
  for (const s of incomplete) {
    if (result.length >= MAX_SUGGESTIONS) break;
    result.push({
      id: `continue-${s.id}`,
      type: 'continue',
      text: `Continue: ${s.chief_complaint || s.title}`,
      icon: 'stethoscope',
      accent: 'warning',
      sessionId: s.id,
      sessionType: 'diagnosis',
    });
  }

  // 2. Recent completed diagnoses (max 1)
  const completed = diagnosisSessions
    .filter((s) => s.diagnosis_state?.phase === 'complete' && isWithinDays(s.updated_at, 14))
    .slice(0, 1);
  for (const s of completed) {
    if (result.length >= MAX_SUGGESTIONS) break;
    result.push({
      id: `followup-${s.id}`,
      type: 'follow_up',
      text: `Follow up: ${s.chief_complaint}`,
      icon: 'doc-search',
      accent: 'success',
      sessionId: s.id,
      sessionType: 'diagnosis',
    });
  }

  // 3. Recent chat topics (max 1)
  const recentChats = chatSessions
    .filter((c) => c.topic && isWithinDays(c.updated_at, 14))
    .slice(0, 1);
  for (const c of recentChats) {
    if (result.length >= MAX_SUGGESTIONS) break;
    result.push({
      id: `followup-${c.id}`,
      type: 'follow_up',
      text: `More on ${c.topic}`,
      icon: 'chat-bubbles',
      accent: 'success',
      sessionId: c.id,
      sessionType: 'chat',
    });
  }

  // 4. Profile conditions (max 2)
  const conditions = profile?.medical_conditions?.slice(0, 2) ?? [];
  for (const cond of conditions) {
    if (result.length >= MAX_SUGGESTIONS) break;
    const label = isSelf ? `${cond.name} check-in` : `${pName}'s ${cond.name} check-in`;
    result.push({
      id: `condition-${cond.name}`,
      type: 'condition',
      text: label,
      icon: 'heart-clipboard',
      accent: 'primary',
    });
  }

  // 5. Profile medications (max 1)
  const meds = profile?.medications?.slice(0, 1) ?? [];
  for (const med of meds) {
    if (result.length >= MAX_SUGGESTIONS) break;
    const label = isSelf ? `${med.name} side effects` : `${pName}'s ${med.name} side effects`;
    result.push({
      id: `medication-${med.name}`,
      type: 'medication',
      text: label,
      icon: 'medkit',
      accent: 'primary',
    });
  }

  // 6. Fill remaining with shuffled generic pool (filtered by profile data)
  if (result.length < MAX_SUGGESTIONS) {
    const rawPool = mode === 'chat' ? CHAT_POOL : DIAGNOSIS_POOL;
    const pool = rawPool.filter((p) => {
      if (p.needs === 'medications' && !hasMeds) return false;
      if (p.needs === 'conditions' && !hasConds) return false;
      if (p.needs === 'allergies' && !hasAllergies) return false;
      return true;
    });
    const shuffled = shuffle(pool);
    const needed = MAX_SUGGESTIONS - result.length;
    for (let i = 0; i < needed && i < shuffled.length; i++) {
      const { needs: _, ...entry } = shuffled[i];
      result.push({ ...entry, id: `generic-${i}` });
    }
  }

  return result;
}
