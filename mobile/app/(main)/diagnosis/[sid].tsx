import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text } from 'react-native';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Stack } from 'expo-router';
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
  const { sid } = useLocalSearchParams<{ sid: string }>();
  const keyRef = useRef({ sid, key: sid === 'new' ? `new-${Date.now()}` : sid });

  if (sid !== keyRef.current.sid) {
    const wasNew = keyRef.current.sid === 'new';
    if (wasNew && sid !== 'new') {
      keyRef.current = { ...keyRef.current, sid };
    } else {
      keyRef.current = { sid, key: sid === 'new' ? `new-${Date.now()}` : sid };
    }
  }

  return <DiagnosisScreenInner key={keyRef.current.key} />;
}

function DiagnosisScreenInner() {
  const Colors = useColors();
  const router = useRouter();
  const qc = useQueryClient();
  const { sid } = useLocalSearchParams<{ sid: string }>();
  const pid = useProfileStore((s) => s.activeProfile?.id) ?? '';
  const isNew = sid === 'new';

  const [activeSid, setActiveSid] = useState<string | null>(isNew ? null : sid);
  const didAutoSend = useRef(false);

  useEffect(() => {
    if (!isNew) setActiveSid(sid);
  }, [sid, isNew]);

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
    activeSid ?? '',
  );

  const serverMessages: LocalMessage[] = (session?.messages ?? []).map((m, i) => ({
    id: `${activeSid ?? sid}-${i}`,
    role: m.role,
    content: m.content,
    contentParts: m.content_parts,
  }));

  const streamSendFn = useCallback(
    (text: string, onEvent: (event: StreamEvent) => void, files?: Attachment[]) => {
      const wrappedOnEvent = (event: StreamEvent) => {
        if (
          event.type === 'status' &&
          'session_id' in event &&
          event.session_id
        ) {
          setActiveSid(event.session_id);
        }
        onEvent(event);
      };
      return diagnosisStreamApi.sendMessage(
        pid,
        text,
        wrappedOnEvent,
        activeSid ?? undefined,
        isNew && !activeSid ? text : undefined,
        files,
      );
    },
    [pid, activeSid, isNew],
  );

  const onSendComplete = useCallback(
    (done?: { session_id?: string }) => {
      const realId = done?.session_id ?? activeSid;
      if (realId && sid !== realId) {
        router.navigate(`/(main)/diagnosis/${realId}` as never);
      }
      qc.invalidateQueries({ queryKey: ['diagnosis', pid] });
      if (realId) {
        qc.invalidateQueries({ queryKey: ['diagnosis', pid, realId] });
      }
    },
    [qc, pid, sid, activeSid, router],
  );

  const conv = useConversation({
    serverMessages,
    streamSendFn,
    dedupMode: 'count',
    onSendComplete,
  });

  useFocusEffect(
    useCallback(() => {
      if (activeSid) refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeSid, refetch]),
  );

  // Abort stream only on true unmount, not on activeSid changes mid-stream
  useEffect(() => {
    return () => conv.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
              <HeaderIconButton icon="pen-square" onPress={() => router.navigate('/(main)' as never)} />
            </View>
          ),
        }}
      />
      <ConversationView
        {...conv}
        onChangeText={conv.setInput}
        onAttach={conv.handleAttach}
        hasAttachment={!!conv.pendingAttachment}
        isLoading={!!activeSid && isLoading && !conv.isBusy}
        error={isNew ? null : error}
        refetch={refetch}
        errorIcon="stethoscope"
        errorTitle="Couldn't load session"
        placeholder="Describe your symptoms…"
      />
    </>
  );
}
