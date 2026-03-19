import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { AppState, FlatList } from 'react-native';
import { useAttachMenu, type Attachment } from '@/hooks/useAttachMenu';
import { logger } from '@/services/logger';
import type { StreamEvent, AgentStep, MessagePart } from '@/types/api';
import { RateLimitError } from '@/services/api';
import type { StreamHandle } from '@/services/api';

export interface SendError {
  message: string;
  retryAfter?: number;
}

export interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  contentParts?: MessagePart[];
  /** Hidden user messages (e.g. structured responses) — still sent to backend but not rendered as bubbles. */
  hidden?: boolean;
}

type DoneEvent = Extract<StreamEvent, { type: 'done' }>;

const TOOL_LABELS: Record<string, string> = {
  web_search: 'Searching the web',
  search_patient_memory: 'Searching memory',
  present_question: 'Preparing question',
  present_assessment: 'Preparing assessment',
  profile_lookup: 'Looking up profile',
};

function toolMessage(name: string): string {
  return `${TOOL_LABELS[name] ?? `Using ${name.replace(/_/g, ' ')}`}...`;
}


export type StreamSendFn = (
  text: string,
  onEvent: (event: StreamEvent) => void,
  files?: Attachment[],
  structuredResponse?: Record<string, unknown>,
) => StreamHandle;

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
  const [sendErrorCount, setSendErrorCount] = useState(0);
  const [sendError, setSendError] = useState<SendError | null>(null);
  const [awaitingServer, setAwaitingServer] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [thinkingContent, setThinkingContent] = useState('');
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const flatListRef = useRef<FlatList>(null);
  const isSendingRef = useRef(false);
  const streamingContentRef = useRef('');
  const thinkingContentRef = useRef('');
  const agentStepsRef = useRef<AgentStep[]>([]);
  const activeAbortRef = useRef<(() => void) | null>(null);
  const structuredQuestionsRef = useRef<MessagePart[]>([]);
  const assessmentRef = useRef<MessagePart | null>(null);
  /** Set to true when app goes to background while a stream is active.
   *  Checked in the catch block — more reliable than reading AppState
   *  at error time, since iOS resumes JS only after returning to foreground. */
  const backgroundedWhileSendingRef = useRef(false);

  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state !== 'active' && isSendingRef.current) {
        backgroundedWhileSendingRef.current = true;
      }
    });
    return () => sub.remove();
  }, []);

  const handleAttach = useAttachMenu((attachment) => setPendingAttachment(attachment));

  // Stable dependency: only re-run dedup when the actual server message IDs change.
  const serverIdKey = serverMessages.map((m) => m.id).join(',');

  useEffect(() => {
    if (pendingMessages.length === 0) return;

    if (dedupMode === 'id') {
      const serverIds = new Set(serverMessages.map((m) => m.id));
      // Last server user message content — used for fallback dedup.
      // Only match the LAST one to avoid false positives when the user
      // sends the same text multiple times (e.g. "Yes").
      const lastServerUser = [...serverMessages].reverse().find((m) => m.role === 'user');
      const lastServerUserContent = lastServerUser?.content;
      setPendingMessages((prev) => {
        // Primary: remove by matching server ID (normal success path)
        let next = prev.filter((m) => !serverIds.has(m.id));
        // Fallback: remove the pending user message if its content matches
        // the latest server user message. Handles error-path messages that
        // have temporary Date.now() IDs (e.g. stream interrupted by
        // app backgrounding — server persisted but IDs don't match).
        if (next.length > 0 && lastServerUserContent) {
          const idx = next.findIndex(
            (m) => m.role === 'user' && m.content === lastServerUserContent,
          );
          if (idx >= 0) {
            // Remove matched user message and any orphaned assistant
            // messages after it (stale partials from interrupted streams).
            next = next.slice(0, idx);
          }
        }
        return next.length === prev.length ? prev : next;
      });
    } else {
      if (serverMessages.length > 0) {
        setPendingMessages([]);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverIdKey, dedupMode]);

  // Clear "awaiting server" once the server's latest message is an assistant
  // response — meaning the backend finished and persisted the result.
  useEffect(() => {
    if (!awaitingServer) return;
    const last = serverMessages[serverMessages.length - 1];
    if (last?.role === 'assistant') {
      logger.info('stream', 'Server response arrived, clearing awaitingServer');
      setAwaitingServer(false);
    }
  // serverIdKey is derived from serverMessages — when it changes, new data arrived.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awaitingServer, serverIdKey]);

  const allMessages = useMemo(() => {
    // Hide user messages that are structured responses (selection shown on the question UI instead)
    const isVisible = (m: LocalMessage) => !m.hidden;
    if (pendingMessages.length === 0) {
      return serverMessages.filter(isVisible);
    }
    const serverIds = new Set(serverMessages.map((m) => m.id));
    const uniquePending = pendingMessages.filter((m) => !serverIds.has(m.id));
    return [...serverMessages, ...uniquePending].filter(isVisible);
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
          const next = [
            ...updated,
            { id: event.step, message: event.message, tool: event.tool, details: event.details, status: 'active' as const },
          ];
          agentStepsRef.current = next;
          return next;
        });
        break;
      case 'tool_call':
        setAgentSteps((prev) => {
          const updated = prev.map((s) =>
            s.status === 'active' ? { ...s, status: 'done' as const } : s,
          );
          const next = [
            ...updated,
            { id: `tc_${event.tool}`, message: toolMessage(event.tool), tool: event.tool, status: 'active' as const },
          ];
          agentStepsRef.current = next;
          return next;
        });
        break;
      case 'tool_result':
        setAgentSteps((prev) => {
          const next = prev.map((s) =>
            s.tool === event.tool && s.status === 'active'
              ? { ...s, message: event.summary, status: 'done' as const }
              : s,
          );
          agentStepsRef.current = next;
          return next;
        });
        break;
      case 'thinking_delta':
        thinkingContentRef.current += event.content;
        setThinkingContent(thinkingContentRef.current);
        break;
      case 'text_delta':
        streamingContentRef.current += event.content;
        setStreamingContent(streamingContentRef.current);
        break;
      case 'structured_question':
        structuredQuestionsRef.current.push({
          type: 'structured_input' as const,
          input_type: event.input_type,
          prompt: event.prompt,
          options: event.options as Array<Record<string, unknown>> | undefined,
          range: event.range as Record<string, unknown> | undefined,
        });
        break;
      case 'structured_assessment':
        assessmentRef.current = {
          type: 'assessment' as const,
          conditions: event.conditions,
          self_care: event.self_care ?? [],
          medications: event.medications ?? [],
          tests: event.tests ?? [],
          warnings: event.warnings ?? [],
          follow_up: event.follow_up,
          sources: event.sources,
        };
        break;
    }
  }, []);

  /** Abort any in-flight stream. Safe to call multiple times. */
  const abort = useCallback(() => {
    activeAbortRef.current?.();
    activeAbortRef.current = null;
  }, []);

  /** Core send logic — used by both onSend (from input) and sendMessage (programmatic). */
  const doSend = useCallback(
    async (text: string, files?: Attachment[], structuredResponse?: Record<string, unknown>) => {
      if (isSendingRef.current) return;
      isSendingRef.current = true;

      const userParts: MessagePart[] = [];
      if (files?.length) {
        for (const f of files) {
          userParts.push({ type: 'image' as const, url: f.uri, mime_type: f.type, filename: f.name });
        }
      }
      if (text.trim()) {
        userParts.push({ type: 'text' as const, text });
      }
      if (structuredResponse) {
        userParts.push({
          type: 'structured_input' as const,
          input_type: structuredResponse.input_type as string,
          prompt: structuredResponse.prompt as string,
          selected: structuredResponse.selected,
        });
      }
      const userMsg: LocalMessage = {
        id: Date.now().toString(),
        role: 'user',
        content: text,
        contentParts: userParts.length > 0 ? userParts : undefined,
        hidden: !!structuredResponse,
      };
      setPendingMessages((prev) => [...prev, userMsg]);

      setIsSending(true);
      setSendError(null);
      setStreamingContent('');
      streamingContentRef.current = '';
      agentStepsRef.current = [];
      structuredQuestionsRef.current = [];
      assessmentRef.current = null;
      setAgentSteps([]);

      let doneEvent: DoneEvent | undefined;

      try {
        const handle = streamSendFn(text, handleStreamEvent, files, structuredResponse);
        activeAbortRef.current = handle.abort;
        const done = await handle.promise;
        activeAbortRef.current = null;
        doneEvent = done;

        setDisclaimer(done.disclaimer ?? null);

        const serverUserId = done.user_message_id;
        // Build contentParts from accumulated agent steps so they render
        // inline immediately — prevents a flash when footer steps clear
        // before server data arrives with persisted content_parts.
        const steps = agentStepsRef.current;
        const parts: MessagePart[] = [];
        if (thinkingContentRef.current) {
          parts.push({ type: 'thinking' as const, text: thinkingContentRef.current });
        }
        if (steps.length > 0) {
          parts.push({
            type: 'agent_steps' as const,
            steps: steps.map((s) => ({ id: s.id, message: s.message, tool: s.tool, details: s.details })),
          });
        }
        // Include assessment part if present (replaces text for assessment turns)
        if (assessmentRef.current) {
          parts.push(assessmentRef.current);
        } else {
          parts.push({ type: 'text' as const, text: done.content });
        }
        // Include structured questions accumulated during streaming
        for (const sq of structuredQuestionsRef.current) {
          parts.push(sq);
        }
        const aiMsg: LocalMessage = {
          id: done.id ?? (Date.now() + 1).toString(),
          role: 'assistant',
          content: done.content,
          contentParts: parts,
        };
        setPendingMessages((prev) => {
          const updated = serverUserId
            ? prev.map((m) => (m.id === userMsg.id ? { ...m, id: serverUserId } : m))
            : prev;
          return [...updated, aiMsg];
        });
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : 'Unknown error';
        const aborted = errMsg === 'Stream aborted';
        // "Stream interrupted" = XHR had a 200 connection that got killed
        // (iOS backgrounding). More reliable than AppState timing alone.
        const interrupted = errMsg === 'Stream interrupted';
        const backgrounded = backgroundedWhileSendingRef.current || interrupted;
        logger.error('stream', 'Send failed', { error: errMsg, had_partial: !!streamingContentRef.current, backgrounded, aborted, interrupted });
        // Auto-report to server for correlation with server-side logs
        if (!aborted) logger.reportToServer({ last: 20 });

        if (backgrounded || aborted) {
          // Backgrounded: backend keeps processing, React Query refetches
          // on foreground return via focusManager.
          // Aborted: user navigated away, component is unmounting — backend
          // still completes and persists. No UI needed.
          logger.info('stream', `Suppressing error UI — ${aborted ? 'stream aborted (navigation)' : 'app backgrounded'}`);
          // Show typing indicator while we poll for the server's response
          if (!aborted) setAwaitingServer(true);
        } else {
          setSendErrorCount((c) => c + 1);
          const partial = streamingContentRef.current;
          if (partial) {
            // Stream interrupted after some content — preserve what we got
            setPendingMessages((prev) => [
              ...prev,
              { id: (Date.now() + 1).toString(), role: 'assistant', content: partial },
            ]);
          } else {
            // No content received — show error banner above input, remove pending user message
            const retryAfter = err instanceof RateLimitError ? err.retryAfter : undefined;
            const message = err instanceof RateLimitError
              ? 'You\u2019re sending messages too quickly'
              : err instanceof Error ? err.message : 'Something went wrong';
            setSendError({ message, retryAfter });
            setPendingMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
          }
        }
      } finally {
        setIsSending(false);
        setStreamingContent('');
        streamingContentRef.current = '';
        setThinkingContent('');
        thinkingContentRef.current = '';
        setAgentSteps([]);
        agentStepsRef.current = [];
        structuredQuestionsRef.current = [];
        assessmentRef.current = null;
        isSendingRef.current = false;
        activeAbortRef.current = null;
        backgroundedWhileSendingRef.current = false;
        onSendComplete?.(doneEvent);
      }

      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    },
    [streamSendFn, handleStreamEvent, onSendComplete],
  );

  /** Send from the input field (reads current input + attachment state). */
  const onSend = useCallback(async () => {
    const text = input.trim();
    if (!text && !pendingAttachment) return;
    setInput('');
    const files = pendingAttachment ? [pendingAttachment] : undefined;
    setPendingAttachment(null);
    // Backend requires non-empty content; use space for image-only sends
    await doSend(text || ' ', files);
  }, [input, pendingAttachment, doSend]);

  /** Programmatic send — for auto-sending the initial message on new conversations. */
  const sendMessage = useCallback(
    (text: string, files?: Attachment[]) => doSend(text, files),
    [doSend],
  );

  /** Send a structured response (from StructuredInputView selection). */
  const onStructuredResponse = useCallback(
    (content: string, structuredResponse: Record<string, unknown>) => {
      doSend(content, undefined, structuredResponse);
    },
    [doSend],
  );

  return {
    allMessages,
    pendingIds,
    input,
    setInput,
    onSend,
    sendMessage,
    onStructuredResponse,
    abort,
    disclaimer,
    pendingAttachment,
    handleAttach,
    clearAttachment: useCallback(() => setPendingAttachment(null), []),
    isBusy: isSending || awaitingServer,
    flatListRef,
    streamingContent,
    thinkingContent,
    agentSteps,
    isStreaming,
    sendErrorCount,
    sendError,
    clearSendError: useCallback(() => setSendError(null), []),
  };
}
