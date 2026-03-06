import { useCallback, useEffect, useMemo, useRef } from 'react';
import { View, Text } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import { ConversationView } from '@/components/ConversationView';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { useProfileStore } from '@/stores/profile';
import { useDiagnosisSession } from '@/hooks/useDiagnosis';
import { useConversation, type LocalMessage } from '@/hooks/useConversation';
import { diagnosisStreamApi } from '@/services/api';
import { consumePendingSend } from '@/services/pendingSend';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { StreamEvent } from '@/types/api';
import type { Attachment } from '@/hooks/useAttachMenu';

export default function DiagnosisScreen() {
  const Colors = useColors();
  const router = useRouter();
  const qc = useQueryClient();
  const { sid } = useLocalSearchParams<{ sid: string }>();
  const pid = useProfileStore((s) => s.activeProfile?.id) ?? '';
  const isNew = sid === 'new';
  const realSidRef = useRef<string | null>(null);
  const didAutoSend = useRef(false);

  const PHASE_LABELS = useMemo(
    () =>
      ({
        gathering: { label: 'Gathering info', color: Colors.info },
        analyzing: { label: 'Analyzing', color: Colors.warning },
        complete: { label: 'Complete', color: Colors.success },
      }) as Record<string, { label: string; color: string }>,
    [Colors],
  );

  const { data: session, isLoading, error, refetch } = useDiagnosisSession(
    pid,
    isNew ? '' : sid,
  );

  const serverMessages: LocalMessage[] = (session?.messages ?? []).map((m, i) => ({
    id: `${sid}-${i}`,
    role: m.role,
    content: m.content,
  }));

  // Reset refs when navigating to a new session (refs persist across param changes)
  useEffect(() => {
    if (sid === 'new') {
      realSidRef.current = null;
      didAutoSend.current = false;
    }
  }, [sid]);

  // Mirrors chat's streamSendFn — intercepts session_id from early status event
  const streamSendFn = useCallback(
    (text: string, onEvent: (event: StreamEvent) => void, files?: Attachment[]) => {
      const wrappedOnEvent = (event: StreamEvent) => {
        // Only replace URL when the server-assigned ID differs from the current URL
        // (i.e., new sessions getting their real ID). For existing sessions,
        // event.session_id === sid so this is skipped.
        if (
          event.type === 'status' &&
          'session_id' in event &&
          event.session_id &&
          event.session_id !== sid
        ) {
          realSidRef.current = event.session_id;
          router.replace(`/(main)/diagnosis/${event.session_id}`);
        }
        onEvent(event);
      };
      const existingSid = realSidRef.current ?? (isNew ? undefined : sid);
      return diagnosisStreamApi.sendMessage(
        pid,
        text,
        wrappedOnEvent,
        existingSid,
        isNew && !realSidRef.current ? text : undefined,
        files,
      );
    },
    [pid, sid, isNew, router],
  );

  const onSendComplete = useCallback(
    (done?: { session_id?: string }) => {
      // Fallback: replace URL from done event if status event didn't arrive
      if (done?.session_id && !realSidRef.current) {
        realSidRef.current = done.session_id;
        router.replace(`/(main)/diagnosis/${done.session_id}`);
      }
      const activeSid = realSidRef.current ?? sid;
      qc.invalidateQueries({ queryKey: ['diagnosis', pid] });
      if (activeSid && activeSid !== 'new') {
        qc.invalidateQueries({ queryKey: ['diagnosis', pid, activeSid] });
      }
    },
    [qc, pid, sid, router],
  );

  const conv = useConversation({
    serverMessages,
    streamSendFn,
    dedupMode: 'count',
    onSendComplete,
  });

  // Auto-send — identical pattern to chat/[cid].tsx
  useEffect(() => {
    if (!isNew || didAutoSend.current) return;
    const pending = consumePendingSend();
    if (!pending) return;
    didAutoSend.current = true;
    conv.sendMessage(pending.text, pending.files);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew]);

  const phase = session?.diagnosis_state?.phase;
  const phaseInfo = phase ? PHASE_LABELS[phase] : undefined;

  return (
    <>
      <Stack.Screen
        options={{
          title: session?.chief_complaint || 'AI Diagnosis',
          headerRight: () => (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.sm }}>
              {phaseInfo && (
                <View
                  style={{
                    backgroundColor: phaseInfo.color + '18',
                    paddingHorizontal: Spacing.sm,
                    paddingVertical: Spacing.xs,
                    borderRadius: BorderRadius.full,
                    borderCurve: 'continuous',
                  }}
                >
                  <Text
                    style={{
                      fontSize: FontSize.xs,
                      fontWeight: FontWeight.semibold,
                      color: phaseInfo.color,
                    }}
                  >
                    {phaseInfo.label}
                  </Text>
                </View>
              )}
              <HeaderIconButton icon="pen-square" onPress={() => router.push('/(main)')} />
            </View>
          ),
        }}
      />
      <ConversationView
        {...conv}
        onChangeText={conv.setInput}
        onAttach={conv.handleAttach}
        hasAttachment={!!conv.pendingAttachment}
        isLoading={!isNew && isLoading}
        error={isNew ? null : error}
        refetch={refetch}
        errorIcon="stethoscope"
        errorTitle="Couldn't load session"
        placeholder="Describe your symptoms…"
      />
    </>
  );
}
