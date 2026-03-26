import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, Pressable, useWindowDimensions } from 'react-native';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Stack } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import Animated, { useSharedValue, useAnimatedStyle, withTiming, Easing } from 'react-native-reanimated';
import { ConversationView } from '@/components/ConversationView';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { AnimatedSalkIcon } from '@/components/AnimatedSalkIcon';
import { useHeaderScale } from '@/hooks/useHeaderScale';
import { useHapticPress } from '@/hooks/useHapticPress';
import { useProfileStore } from '@/stores/profile';
import { useDiagnosisSession } from '@/hooks/useDiagnosis';
import { useConversation, type LocalMessage } from '@/hooks/useConversation';
import { diagnosisStreamApi } from '@/services/api';
import { consumePendingSend } from '@/services/pendingSend';
import { useNavSource } from '@/services/navigationSource';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { StreamEvent } from '@/types/api';
import type { Attachment } from '@/hooks/useAttachMenu';

export default function DiagnosisScreen() {
  const { sid } = useLocalSearchParams<{ sid: string }>();
  const keyRef = useRef({ sid, key: sid });

  if (sid !== keyRef.current.sid) {
    const wasNew = keyRef.current.sid?.startsWith('new') ?? false;
    const nowNew = sid?.startsWith('new') ?? false;
    if (wasNew && !nowNew) {
      keyRef.current = { ...keyRef.current, sid };
    } else {
      keyRef.current = { sid, key: sid };
    }
  }

  return <DiagnosisScreenInner key={keyRef.current.key} />;
}

function DiagnosisScreenInner() {
  const header = useHeaderScale();
  const Colors = useColors();
  const router = useRouter();
  const handleNewSession = useHapticPress(() => router.navigate('/(main)' as never));
  const qc = useQueryClient();
  const { sid } = useLocalSearchParams<{ sid: string }>();
  const pid = useProfileStore((s) => s.activeProfile?.id) ?? '';
  const isNew = sid?.startsWith('new') ?? false;

  // Zustand-driven: list pages set true, sidebar sets false. Reactive re-render.
  const fromList = useNavSource((s) => s.fromList);

  // Slide in from right when arriving from list
  const { width: screenWidth } = useWindowDimensions();
  // Initialize off-screen when arriving from list — prevents 1-frame flash
  const slideX = useSharedValue(fromList ? screenWidth : 0);
  const slideStyle = useAnimatedStyle(() => ({
    flex: 1,
    transform: [{ translateX: slideX.value }],
  }));
  useFocusEffect(
    useCallback(() => {
      if (fromList) {
        slideX.value = screenWidth;
        slideX.value = withTiming(0, { duration: 300, easing: Easing.out(Easing.cubic) });
      } else {
        slideX.value = 0;
      }
      // On blur: move back off-screen so next focus starts from the right
      return () => {
        if (fromList) slideX.value = screenWidth;
      };
    }, [fromList, slideX, screenWidth]),
  );

  const handleBack = useCallback(() => {
    // fromList stays true — list page reads it for its slide-in animation
    router.navigate('/(main)/diagnosis/all' as never);
  }, [router]);

  const [activeSid, setActiveSid] = useState<string | null>(isNew ? null : sid);
  const didAutoSend = useRef(false);

  useEffect(() => {
    if (!isNew) setActiveSid(sid);
  }, [sid, isNew]);

  // Drawer keeps screens mounted — when the active profile changes,
  // the old session doesn't belong to the new profile.
  // Must be synchronous (not useEffect) because React Query fires
  // during render, before effects run.
  const prevPid = useRef(pid);
  const pidChanged = pid !== prevPid.current;
  useEffect(() => {
    if (pidChanged) {
      prevPid.current = pid;
      setActiveSid(null);
    }
  }, [pid, pidChanged]);

  const PHASE_LABELS = useMemo(
    () =>
      ({
        gathering: { label: 'Gathering info', color: Colors.info },
        analyzing: { label: 'Analyzing', color: Colors.warning },
        complete: { label: 'Complete', color: Colors.success },
      }) as Record<string, { label: string; color: string }>,
    [Colors],
  );

  // Disable query on the same render cycle that pid changes.
  const { data: session, isLoading, error, refetch } = useDiagnosisSession(
    pid,
    pidChanged ? '' : (activeSid ?? ''),
  );

  const serverMessages: LocalMessage[] = useMemo(() => {
    const rawMessages = session?.messages ?? [];
    // Build a map of "prompt::assistantIndex" → selected from user answers.
    // Keyed by assistant index to avoid collision when the same prompt repeats.
    const answerMap = new Map<string, unknown>();
    for (let idx = 0; idx < rawMessages.length; idx++) {
      const m = rawMessages[idx];
      if (m.role === 'user' && m.content_parts) {
        const assistantIdx = rawMessages.slice(0, idx).findLastIndex((msg) => msg.role === 'assistant');
        for (const p of m.content_parts) {
          if (p.type === 'structured_input' && p.selected != null) {
            answerMap.set(`${p.prompt}::${assistantIdx}`, p.selected);
          }
        }
      }
    }
    return rawMessages.map((m, i) => {
      const isStructuredUser = m.role === 'user' && m.content_parts?.some((p) => p.type === 'structured_input');
      // Merge user selections onto assistant question parts
      let parts = m.content_parts;
      if (m.role === 'assistant' && parts && answerMap.size > 0) {
        parts = parts.map((p) =>
          p.type === 'structured_input' && p.selected == null && answerMap.has(`${p.prompt}::${i}`)
            ? { ...p, selected: answerMap.get(`${p.prompt}::${i}`) }
            : p,
        );
      }
      return {
        id: `${activeSid ?? sid}-${i}`,
        role: m.role,
        content: m.content,
        contentParts: parts,
        hidden: isStructuredUser,
      };
    });
  }, [session?.messages, activeSid, sid]);

  const streamSendFn = useCallback(
    (text: string, onEvent: (event: StreamEvent) => void, files?: Attachment[], structuredResponse?: Record<string, unknown>) => {
      const wrappedOnEvent = (event: StreamEvent) => {
        if (
          event.type === 'status' &&
          'session_id' in event &&
          event.session_id
        ) {
          setActiveSid(event.session_id);
          qc.invalidateQueries({ queryKey: ['diagnosis', pid] });
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
        structuredResponse,
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
      if (realId) {
        qc.invalidateQueries({ queryKey: ['diagnosis', pid, realId] });
      }
      // Re-fetch session list so sidebar picks up auto-generated title
      // (written server-side after the DONE event).
      setTimeout(() => qc.invalidateQueries({ queryKey: ['diagnosis', pid] }), 3000);
    },
    [qc, pid, sid, activeSid, router],
  );

  const conv = useConversation({
    serverMessages,
    streamSendFn,
    dedupMode: 'count',
    onSendComplete,
  });


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
          title: session?.title || session?.chief_complaint || 'AI Diagnosis',
          headerLeft: fromList
            ? () => <HeaderIconButton icon="chevron-back" onPress={handleBack} />
            : undefined,
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
              <Pressable onPress={handleNewSession} style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
                <AnimatedSalkIcon size={header.buttonSize} showBackground={false} />
              </Pressable>
            </View>
          ),
        }}
      />
      <Animated.View style={slideStyle}>
        <ConversationView
          {...conv}
          onChangeText={conv.setInput}
          onAttach={conv.handleAttach}
          pendingAttachment={conv.pendingAttachment}
          onRemoveAttachment={() => conv.clearAttachment()}
          isLoading={!!activeSid && !session && !error && !conv.isBusy}
          error={isNew ? null : error}
          refetch={refetch}
          errorIcon="stethoscope"
          errorTitle="Couldn't load session"
          placeholder="Describe your symptoms…"
          mode="diagnosis"
          onStructuredResponse={conv.onStructuredResponse}
          onDismissError={conv.clearSendError}
        />
      </Animated.View>
    </>
  );
}
