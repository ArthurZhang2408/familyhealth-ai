import { useMemo, useEffect } from 'react';
import { useProfileStore } from '@/stores/profile';
import { useChatConversations } from '@/hooks/useChat';
import { useDiagnosisSessions } from '@/hooks/useDiagnosis';
import {
  buildSuggestions,
  getCachedSuggestions,
  setCachedSuggestions,
  cacheKey,
  type Suggestion,
} from '@/services/suggestions';

export type { Suggestion } from '@/services/suggestions';

export function usePromptSuggestions(mode: 'chat' | 'diagnosis') {
  const profile = useProfileStore((s) => s.activeProfile);
  const pid = profile?.id ?? '';
  const key = cacheKey(pid, mode);

  const { data: chatData } = useChatConversations(pid);
  const { data: dxData } = useDiagnosisSessions(pid);

  const suggestions = useMemo(() => {
    if (!pid) return [];
    const cached = getCachedSuggestions(key);
    if (cached) return cached;
    if (!chatData && !dxData) return [];
    return buildSuggestions(mode, profile, chatData?.items ?? [], dxData?.items ?? []);
  }, [key, pid, mode, profile, chatData, dxData]);

  // Persist to module cache as a side effect
  useEffect(() => {
    if (suggestions.length > 0 && !getCachedSuggestions(key)) {
      setCachedSuggestions(key, suggestions);
    }
  }, [key, suggestions]);

  return { suggestions, isLoading: pid !== '' && suggestions.length === 0 };
}
