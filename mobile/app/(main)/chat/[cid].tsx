import { useCallback, useEffect, useRef, useState } from 'react';
import { useWindowDimensions } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Stack } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { Springs } from '@/constants/animations';
import { ConversationView } from '@/components/ConversationView';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { useProfileStore } from '@/stores/profile';
import { useChatConversation } from '@/hooks/useChat';
import { useConversation, type LocalMessage } from '@/hooks/useConversation';
import { chatApi } from '@/services/api';
import { consumePendingSend } from '@/services/pendingSend';
import { useNavSource } from '@/services/navigationSource';
import type { StreamEvent } from '@/types/api';
import type { Attachment } from '@/hooks/useAttachMenu';

/**
 * Outer shell: forces a full remount of ChatScreenInner when `cid` changes.
 * In a Drawer navigator, this is a single component instance that receives
 * different params — the key ensures fresh state for each conversation.
 */
export default function ChatScreen() {
  const { cid } = useLocalSearchParams<{ cid: string }>();
  const keyRef = useRef({ cid, key: cid });

  if (cid !== keyRef.current.cid) {
    const wasNew = keyRef.current.cid?.startsWith('new') ?? false;
    const nowNew = cid?.startsWith('new') ?? false;
    if (wasNew && !nowNew) {
      // new → real ID: preserve state (stream still in progress or just finished)
      keyRef.current = { ...keyRef.current, cid };
    } else {
      // Any other transition (different conversation, or navigating to 'new-<ts>'): remount
      keyRef.current = { cid, key: cid };
    }
  }

  return <ChatScreenInner key={keyRef.current.key} />;
}

function ChatScreenInner() {
  const router = useRouter();
  const qc = useQueryClient();
  const { cid } = useLocalSearchParams<{ cid: string }>();
  const pid = useProfileStore((s) => s.activeProfile?.id) ?? '';
  const isNew = cid?.startsWith('new') ?? false;

  // Zustand-driven: list pages set true, sidebar sets false. Reactive re-render.
  const fromList = useNavSource((s) => s.fromList);

  // Slide in from right when arriving from list
  const { width: screenWidth } = useWindowDimensions();
  const slideX = useSharedValue(0);
  const slideStyle = useAnimatedStyle(() => ({
    flex: 1,
    transform: [{ translateX: slideX.value }],
  }));
  const prevFromList = useRef(false);
  useEffect(() => {
    if (fromList && !prevFromList.current) {
      slideX.value = screenWidth;
      slideX.value = withSpring(0, Springs.gentle);
    } else if (!fromList) {
      slideX.value = 0;
    }
    prevFromList.current = fromList;
  }, [fromList, slideX, screenWidth]);

  const handleBack = useCallback(() => {
    // fromList stays true — list page reads it for its slide-in animation
    router.navigate('/(main)/chat/all' as never);
  }, [router]);

  // State-based ID tracking: avoids router.replace during streaming.
  // Set from the stream's status event so the query can fetch real data
  // even while the URL still shows 'new'.
  const [activeCid, setActiveCid] = useState<string | null>(isNew ? null : cid);
  const activeCidRef = useRef(activeCid);
  activeCidRef.current = activeCid;
  const didAutoSend = useRef(false);

  // Sync activeCid when cid changes via navigation (e.g., sidebar tap)
  useEffect(() => {
    if (!isNew) setActiveCid(cid);
  }, [cid, isNew]);

  // Drawer keeps screens mounted — when the active profile changes,
  // the old conversation doesn't belong to the new profile.
  // Must be synchronous (not useEffect) because React Query fires
  // during render, before effects run.
  const prevPid = useRef(pid);
  const pidChanged = pid !== prevPid.current;
  useEffect(() => {
    if (pidChanged) {
      prevPid.current = pid;
      setActiveCid(null);
    }
  }, [pid, pidChanged]);

  // Disable query on the same render cycle that pid changes —
  // don't wait for the effect to clear activeCid.
  const { data: conversation, isLoading, error, refetch } = useChatConversation(
    pid,
    pidChanged ? '' : (activeCid ?? ''),
  );

  // Retry-poll: when the stream fails while backgrounded, the backend
  // may still be generating. Poll until the assistant response appears.
  const retryPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearRetryPoll = useCallback(() => {
    if (retryPollRef.current) {
      clearInterval(retryPollRef.current);
      retryPollRef.current = null;
    }
  }, []);

  // Clean up poll on unmount
  useEffect(() => clearRetryPoll, [clearRetryPoll]);

  const serverMessages: LocalMessage[] = (conversation?.messages ?? []).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    contentParts: m.content_parts,
  }));

  // Stop retry-poll once the server returns the assistant response
  const lastServerRole = serverMessages.length > 0 ? serverMessages[serverMessages.length - 1].role : null;
  useEffect(() => {
    if (lastServerRole === 'assistant' && retryPollRef.current) {
      clearRetryPoll();
    }
  }, [lastServerRole, clearRetryPoll]);

  const streamSendFn = useCallback(
    (text: string, onEvent: (event: StreamEvent) => void, files?: Attachment[]) => {
      const wrappedOnEvent = (event: StreamEvent) => {
        // Capture the real conversation ID from the first status event.
        // Don't navigate yet — just update state so the query starts fetching.
        if (
          event.type === 'status' &&
          'conversation_id' in event &&
          event.conversation_id
        ) {
          setActiveCid(event.conversation_id);
          // Sync ref immediately — React won't re-render while backgrounded,
          // but onSendComplete needs the latest value from the ref.
          activeCidRef.current = event.conversation_id;
          // Invalidate the conversation list immediately so the sidebar
          // shows the new session while the agent is still responding.
          qc.invalidateQueries({ queryKey: ['chat', pid] });
        }
        onEvent(event);
      };
      return chatApi.sendStream(pid, text, wrappedOnEvent, activeCid ?? undefined, undefined, files);
    },
    [pid, activeCid],
  );

  const onSendComplete = useCallback(
    (done?: { conversation_id?: string }) => {
      // Clear any poll from a previous failed send
      clearRetryPoll();
      // Read from ref to get the latest activeCid — the closure may have
      // captured a stale value from before the status event set it.
      const realId = done?.conversation_id ?? activeCidRef.current;
      // Now that the stream is finished, update the URL to the real ID.
      if (realId && cid !== realId) {
        router.navigate(`/(main)/chat/${realId}` as never);
      }
      if (realId) {
        qc.invalidateQueries({ queryKey: ['chat', pid, realId] });
      }

      // If stream failed (no done event), the backend is likely still
      // processing. Poll every 3s until the assistant response appears
      // (max 30s). This covers both backgrounded disconnects and any
      // other stream interruption where the server continues.
      if (!done && realId) {
        let attempts = 0;
        retryPollRef.current = setInterval(() => {
          attempts++;
          qc.invalidateQueries({ queryKey: ['chat', pid, realId] });
          if (attempts >= 10) clearRetryPoll();
        }, 3000);
      }

      // Re-fetch conversation list so the sidebar picks up the
      // auto-generated topic (written server-side after the DONE event).
      // Delay slightly to give the server time to commit the topic.
      setTimeout(() => qc.invalidateQueries({ queryKey: ['chat', pid] }), 3000);
    },
    [qc, pid, cid, router, clearRetryPoll],
  );

  const conv = useConversation({
    serverMessages,
    streamSendFn,
    dedupMode: 'id',
    onSendComplete,
  });


  // Abort stream only on true unmount (navigating away), NOT on activeCid changes.
  // activeCid changes mid-stream when a new conversation ID arrives — aborting
  // there kills the stream before agent steps and response can flow.
  useEffect(() => {
    return () => conv.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-send the initial message for new conversations
  useEffect(() => {
    if (!isNew || didAutoSend.current) return;
    const pending = consumePendingSend();
    if (!pending) return;
    didAutoSend.current = true;
    conv.sendMessage(pending.text, pending.files);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNew]);

  return (
    <>
      <Stack.Screen
        options={{
          title: conversation?.topic || 'Health Chat',
          headerLeft: fromList
            ? () => <HeaderIconButton icon="chevron-back" onPress={handleBack} />
            : undefined,
          headerRight: () => (
            <HeaderIconButton icon="pen-square" onPress={() => router.navigate('/(main)' as never)} />
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
          isLoading={!!activeCid && !conversation && !error && !conv.isBusy}
          error={isNew ? null : error}
          refetch={refetch}
          placeholder="Ask a health question…"
          onDismissError={conv.clearSendError}
        />
      </Animated.View>
    </>
  );
}
