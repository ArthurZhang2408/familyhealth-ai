import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Stack } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';
import { ConversationView } from '@/components/ConversationView';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { useProfileStore } from '@/stores/profile';
import { useChatConversation } from '@/hooks/useChat';
import { useConversation, type LocalMessage } from '@/hooks/useConversation';
import { chatApi } from '@/services/api';
import { consumePendingSend } from '@/services/pendingSend';
import type { StreamEvent } from '@/types/api';
import type { Attachment } from '@/hooks/useAttachMenu';

/**
 * Outer shell: forces a full remount of ChatScreenInner when `cid` changes.
 * In a Drawer navigator, this is a single component instance that receives
 * different params — the key ensures fresh state for each conversation.
 */
export default function ChatScreen() {
  const { cid } = useLocalSearchParams<{ cid: string }>();
  const keyRef = useRef({ cid, key: cid === 'new' ? `new-${Date.now()}` : cid });

  if (cid !== keyRef.current.cid) {
    const wasNew = keyRef.current.cid === 'new';
    if (wasNew && cid !== 'new') {
      // new → real ID: preserve state (stream still in progress or just finished)
      keyRef.current = { ...keyRef.current, cid };
    } else {
      // Any other transition (different conversation, or navigating to 'new'): remount
      keyRef.current = { cid, key: cid === 'new' ? `new-${Date.now()}` : cid };
    }
  }

  return <ChatScreenInner key={keyRef.current.key} />;
}

function ChatScreenInner() {
  const router = useRouter();
  const qc = useQueryClient();
  const { cid } = useLocalSearchParams<{ cid: string }>();
  const pid = useProfileStore((s) => s.activeProfile?.id) ?? '';
  const isNew = cid === 'new';

  // State-based ID tracking: avoids router.replace during streaming.
  // Set from the stream's status event so the query can fetch real data
  // even while the URL still shows 'new'.
  const [activeCid, setActiveCid] = useState<string | null>(isNew ? null : cid);
  const didAutoSend = useRef(false);

  // Sync activeCid when cid changes via navigation (e.g., sidebar tap)
  useEffect(() => {
    if (!isNew) setActiveCid(cid);
  }, [cid, isNew]);

  const { data: conversation, isLoading, error, refetch } = useChatConversation(
    pid,
    activeCid ?? '',
  );

  const serverMessages: LocalMessage[] = (conversation?.messages ?? []).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
  }));

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
        }
        onEvent(event);
      };
      return chatApi.sendStream(pid, text, wrappedOnEvent, activeCid ?? undefined, undefined, files);
    },
    [pid, activeCid],
  );

  const onSendComplete = useCallback(
    (done?: { conversation_id?: string }) => {
      const realId = done?.conversation_id ?? activeCid;
      // Now that the stream is finished, update the URL to the real ID.
      if (realId && cid !== realId) {
        router.navigate(`/(main)/chat/${realId}` as never);
      }
      qc.invalidateQueries({ queryKey: ['chat', pid] });
      if (realId) {
        qc.invalidateQueries({ queryKey: ['chat', pid, realId] });
      }
    },
    [qc, pid, cid, activeCid, router],
  );

  const conv = useConversation({
    serverMessages,
    streamSendFn,
    dedupMode: 'id',
    onSendComplete,
  });

  // Abort stream when screen loses focus (navigating away / app backgrounded).
  // Refetch when screen regains focus (picks up server-completed responses).
  useFocusEffect(
    useCallback(() => {
      if (activeCid) refetch();
      return () => {
        conv.abort();
      };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeCid, refetch]),
  );

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
          headerRight: () => (
            <HeaderIconButton icon="pen-square" onPress={() => router.navigate('/(main)' as never)} />
          ),
        }}
      />
      <ConversationView
        {...conv}
        onChangeText={conv.setInput}
        onAttach={conv.handleAttach}
        hasAttachment={!!conv.pendingAttachment}
        isLoading={!!activeCid && isLoading}
        error={isNew ? null : error}
        refetch={refetch}
        placeholder="Ask a health question…"
      />
    </>
  );
}
