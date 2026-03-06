import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { FlatList } from 'react-native';
import { useAttachMenu, type Attachment } from '@/hooks/useAttachMenu';
import type { StreamEvent, AgentStep } from '@/types/api';

export interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

type DoneEvent = Extract<StreamEvent, { type: 'done' }>;

export type StreamSendFn = (
  text: string,
  onEvent: (event: StreamEvent) => void,
  files?: Attachment[],
) => Promise<DoneEvent>;

interface UseConversationConfig {
  serverMessages: LocalMessage[];
  streamSendFn: StreamSendFn;
  /** 'id' = filter pending by server IDs (chat). 'count' = wipe all when server grows (diagnosis). */
  dedupMode: 'id' | 'count';
  /** Called after a send completes (success or error). Use to invalidate query cache. */
  onSendComplete?: (done?: DoneEvent) => void;
}

export function useConversation({ serverMessages, streamSendFn, dedupMode, onSendComplete }: UseConversationConfig) {
  const [pendingMessages, setPendingMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState('');
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [pendingAttachment, setPendingAttachment] = useState<Attachment | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const flatListRef = useRef<FlatList>(null);
  const isSendingRef = useRef(false);
  const streamingContentRef = useRef('');

  const handleAttach = useAttachMenu((attachment) => setPendingAttachment(attachment));

  // Stable dependency: only re-run dedup when the actual server message IDs change.
  const serverIdKey = serverMessages.map((m) => m.id).join(',');

  useEffect(() => {
    if (pendingMessages.length === 0) return;

    if (dedupMode === 'id') {
      const serverIds = new Set(serverMessages.map((m) => m.id));
      setPendingMessages((prev) => {
        const next = prev.filter((m) => !serverIds.has(m.id));
        return next.length === prev.length ? prev : next;
      });
    } else {
      if (serverMessages.length > 0) {
        setPendingMessages([]);
      }
    }
  // Only re-run when server data changes — NOT when pending changes.
  // Adding pendingMessages.length here causes 'count' mode to immediately
  // clear pending (since serverMessages.length > 0 for existing sessions),
  // which makes user messages disappear before the AI responds.
  // The allMessages memo already handles display-level dedup.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverIdKey, dedupMode]);

  const allMessages = useMemo(() => {
    if (pendingMessages.length === 0) return serverMessages;
    // Filter out pending messages that already exist in server data (by ID)
    // to prevent duplicate keys even before the dedup effect runs.
    const serverIds = new Set(serverMessages.map((m) => m.id));
    const uniquePending = pendingMessages.filter((m) => !serverIds.has(m.id));
    return [...serverMessages, ...uniquePending];
  }, [serverMessages, pendingMessages]);

  const pendingIds = useMemo(() => {
    const set = new Set<string>();
    for (const m of pendingMessages) set.add(m.id);
    return set;
  }, [pendingMessages]);

  const isStreaming = isSending && streamingContent.length > 0;

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'status':
        setAgentSteps((prev) => {
          const updated = prev.map((s) =>
            s.status === 'active' ? { ...s, status: 'done' as const } : s,
          );
          return [
            ...updated,
            { id: event.step, message: event.message, tool: event.tool, details: event.details, status: 'active' as const },
          ];
        });
        break;
      case 'tool_call':
        setAgentSteps((prev) => {
          const updated = prev.map((s) =>
            s.status === 'active' ? { ...s, status: 'done' as const } : s,
          );
          return [
            ...updated,
            { id: `tc_${event.tool}`, message: `Using ${event.tool}...`, tool: event.tool, status: 'active' as const },
          ];
        });
        break;
      case 'tool_result':
        setAgentSteps((prev) =>
          prev.map((s) =>
            s.tool === event.tool && s.status === 'active'
              ? { ...s, message: event.summary, status: 'done' as const }
              : s,
          ),
        );
        break;
      case 'text_delta':
        streamingContentRef.current += event.content;
        setStreamingContent(streamingContentRef.current);
        break;
    }
  }, []);

  /** Core send logic — used by both onSend (from input) and sendMessage (programmatic). */
  const doSend = useCallback(
    async (text: string, files?: Attachment[]) => {
      if (isSendingRef.current) return;
      isSendingRef.current = true;

      const userMsg: LocalMessage = { id: Date.now().toString(), role: 'user', content: text };
      setPendingMessages((prev) => [...prev, userMsg]);

      setIsSending(true);
      setStreamingContent('');
      streamingContentRef.current = '';
      setAgentSteps([]);

      let doneEvent: DoneEvent | undefined;

      try {
        const done = await streamSendFn(text, handleStreamEvent, files);
        doneEvent = done;

        setDisclaimer(done.disclaimer ?? null);

        const serverUserId = done.user_message_id;
        const aiMsg: LocalMessage = {
          id: done.id ?? (Date.now() + 1).toString(),
          role: 'assistant',
          content: done.content,
        };
        setPendingMessages((prev) => {
          const updated = serverUserId
            ? prev.map((m) => (m.id === userMsg.id ? { ...m, id: serverUserId } : m))
            : prev;
          return [...updated, aiMsg];
        });
      } catch {
        // Stream interrupted (app backgrounded, network lost, etc.).
        // Preserve any partial content that was streamed before the interruption.
        // onSendComplete will refetch — if the backend finished, server data replaces this.
        const partial = streamingContentRef.current;
        if (partial) {
          setPendingMessages((prev) => [
            ...prev,
            { id: (Date.now() + 1).toString(), role: 'assistant', content: partial },
          ]);
        }
      } finally {
        setIsSending(false);
        setStreamingContent('');
        setAgentSteps([]);
        isSendingRef.current = false;
        onSendComplete?.(doneEvent);
      }

      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    },
    [streamSendFn, handleStreamEvent, onSendComplete],
  );

  /** Send from the input field (reads current input + attachment state). */
  const onSend = useCallback(async () => {
    const text = input.trim() || (pendingAttachment ? 'Please look at this image.' : '');
    if (!text) return;
    setInput('');
    const files = pendingAttachment ? [pendingAttachment] : undefined;
    setPendingAttachment(null);
    await doSend(text, files);
  }, [input, pendingAttachment, doSend]);

  /** Programmatic send — for auto-sending the initial message on new conversations. */
  const sendMessage = useCallback(
    (text: string, files?: Attachment[]) => doSend(text, files),
    [doSend],
  );

  return {
    allMessages,
    pendingIds,
    input,
    setInput,
    onSend,
    sendMessage,
    disclaimer,
    pendingAttachment,
    handleAttach,
    isBusy: isSending,
    flatListRef,
    streamingContent,
    agentSteps,
    isStreaming,
  };
}
