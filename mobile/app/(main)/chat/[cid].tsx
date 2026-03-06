import { useCallback, useEffect, useRef } from 'react';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
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

export default function ChatScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { cid } = useLocalSearchParams<{ cid: string }>();
  const pid = useProfileStore((s) => s.activeProfile?.id) ?? '';
  const isNew = cid === 'new';
  const realCidRef = useRef<string | null>(null);
  const didAutoSend = useRef(false);

  // Skip the GET query for new conversations (no server data yet)
  const { data: conversation, isLoading, error, refetch } = useChatConversation(
    pid,
    isNew ? '' : cid,
  );

  const serverMessages: LocalMessage[] = (conversation?.messages ?? []).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
  }));

  // Reset refs when navigating to a new conversation (refs persist across param changes)
  useEffect(() => {
    if (cid === 'new') {
      realCidRef.current = null;
      didAutoSend.current = false;
    }
  }, [cid]);

  const streamSendFn = useCallback(
    (text: string, onEvent: (event: StreamEvent) => void, files?: Attachment[]) => {
      const wrappedOnEvent = (event: StreamEvent) => {
        // Only replace URL when the server-assigned ID differs from the current URL
        if (
          event.type === 'status' &&
          'conversation_id' in event &&
          event.conversation_id &&
          event.conversation_id !== cid
        ) {
          realCidRef.current = event.conversation_id;
          router.replace(`/(main)/chat/${event.conversation_id}`);
        }
        onEvent(event);
      };
      const convId = realCidRef.current ?? (isNew ? undefined : cid);
      return chatApi.sendStream(pid, text, wrappedOnEvent, convId, undefined, files);
    },
    [pid, cid, isNew, router],
  );

  const onSendComplete = useCallback(
    (done?: { conversation_id?: string }) => {
      // Fallback: replace URL from done event if status event didn't arrive
      if (done?.conversation_id && done.conversation_id !== cid) {
        realCidRef.current = done.conversation_id;
        router.replace(`/(main)/chat/${done.conversation_id}`);
      }
      const activeCid = realCidRef.current ?? cid;
      qc.invalidateQueries({ queryKey: ['chat', pid] });
      if (activeCid && activeCid !== 'new') {
        qc.invalidateQueries({ queryKey: ['chat', pid, activeCid] });
      }
    },
    [qc, pid, cid, router],
  );

  const conv = useConversation({
    serverMessages,
    streamSendFn,
    dedupMode: 'id',
    onSendComplete,
  });

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
            <HeaderIconButton icon="pen-square" onPress={() => router.push('/(main)')} />
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
        placeholder="Ask a health question…"
      />
    </>
  );
}
