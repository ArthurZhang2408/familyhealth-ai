import { RefObject, useEffect, useCallback, useMemo, useRef, useState } from 'react';
import { View, Text, Pressable, FlatList } from 'react-native';
import Animated, {
  SlideOutUp,
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withSequence,
  withDelay,
} from 'react-native-reanimated';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { ChatBubble, TypingIndicator } from '@/components/ChatBubble';
import { ChatInput } from '@/components/ChatInput';
import { AgentSteps } from '@/components/AgentSteps';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Icon, type IconName } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { enterSlideUp, enterSlideDown, enterFade, Springs } from '@/constants/animations';
import type { LocalMessage, SendError } from '@/hooks/useConversation';
import type { AgentStep } from '@/types/api';
import type { Attachment } from '@/hooks/useAttachMenu';

interface ConversationViewProps {
  allMessages: LocalMessage[];
  pendingIds: Set<string>;
  input: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  isBusy: boolean;
  disclaimer: string | null;
  flatListRef: RefObject<FlatList | null>;
  placeholder?: string;
  onAttach?: () => void;
  pendingAttachment?: Attachment | null;
  onRemoveAttachment?: () => void;
  isLoading?: boolean;
  error?: Error | null;
  refetch?: () => void;
  errorIcon?: IconName;
  errorTitle?: string;
  streamingContent?: string;
  thinkingContent?: string;
  agentSteps?: AgentStep[];
  isStreaming?: boolean;
  onStructuredResponse?: (content: string, structuredResponse: Record<string, unknown>) => void;
  /** Incremented on each send error — used to reset StructuredInputView selection. */
  sendErrorCount?: number;
  /** Active send error to display as a banner above the input. */
  sendError?: SendError | null;
  /** Called when the user dismisses the error banner. */
  onDismissError?: () => void;
}

export function ConversationView({
  allMessages,
  pendingIds,
  input,
  onChangeText,
  onSend,
  isBusy,
  disclaimer,
  flatListRef,
  placeholder,
  onAttach,
  pendingAttachment,
  onRemoveAttachment,
  isLoading,
  error,
  refetch,
  errorIcon = 'chat-bubbles',
  errorTitle = "Couldn't load conversation",
  streamingContent = '',
  thinkingContent = '',
  agentSteps = [],
  isStreaming = false,
  onStructuredResponse,
  sendErrorCount = 0,
  sendError,
  onDismissError,
}: ConversationViewProps) {
  const Colors = useColors();

  // Inverted FlatList: data newest-first, list renders from the bottom.
  const reversedMessages = useMemo(() => [...allMessages].reverse(), [allMessages]);
  const lastAssistantId = allMessages.findLast((m) => m.role === 'assistant')?.id;

  // Auto-scroll to bottom (offset 0 in inverted list) when streaming
  useEffect(() => {
    if (isStreaming || (isBusy && (agentSteps.length > 0 || thinkingContent.length > 0))) {
      flatListRef.current?.scrollToOffset({ offset: 0, animated: true });
    }
  }, [streamingContent, thinkingContent, agentSteps.length, isStreaming, isBusy, flatListRef]);

  if (isLoading) return <LoadingSpinner />;

  if (error && allMessages.length === 0) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: Colors.background,
          alignItems: 'center',
          justifyContent: 'center',
          padding: Spacing.xl,
        }}
      >
        <Icon name={errorIcon} size={32} color={Colors.textMuted} />
        <Text
          style={{
            fontSize: FontSize.md,
            color: Colors.textSecondary,
            textAlign: 'center',
            marginTop: Spacing.md,
          }}
        >
          {errorTitle}
        </Text>
        <Text
          style={{
            fontSize: FontSize.sm,
            color: Colors.textMuted,
            textAlign: 'center',
            marginTop: Spacing.xs,
          }}
        >
          Check your connection and try again
        </Text>
        <Pressable
          onPress={() => refetch?.()}
          style={({ pressed }) => ({
            marginTop: Spacing.lg,
            backgroundColor: Colors.primary,
            borderRadius: BorderRadius.md,
            borderCurve: 'continuous',
            paddingHorizontal: Spacing.lg,
            paddingVertical: Spacing.sm,
            opacity: pressed ? 0.85 : 1,
          })}
        >
          <Text
            style={{
              fontSize: FontSize.sm,
              fontWeight: FontWeight.semibold,
              color: Colors.textInverse,
            }}
          >
            Retry
          </Text>
        </Pressable>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
        style={{ flex: 1, backgroundColor: Colors.background }}
        behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        <FlatList
          ref={flatListRef}
          inverted
          data={reversedMessages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{
            padding: Spacing.md,
            gap: Spacing.sm,
            flexGrow: 1,
            justifyContent: allMessages.length === 0 ? 'center' : 'flex-start',
          }}
          contentInsetAdjustmentBehavior="automatic"
          renderItem={({ item }) => {
            const isLatestAssistant = item.role === 'assistant' && item.id === lastAssistantId;
            return (
              <ChatBubble
                content={item.content}
                contentParts={item.contentParts}
                isUser={item.role === 'user'}
                animate={pendingIds.has(item.id)}
                onStructuredResponse={onStructuredResponse}
                isLatestAssistant={isLatestAssistant}
                sendErrorCount={sendErrorCount}
              />
            );
          }}
          ListEmptyComponent={
            !isBusy ? (
              <View style={{ alignItems: 'center', padding: Spacing.xl }}>
                <Text
                  style={{
                    fontSize: FontSize.md,
                    color: Colors.textMuted,
                    textAlign: 'center',
                  }}
                >
                  No messages yet
                </Text>
              </View>
            ) : null
          }
          ListHeaderComponent={
            allMessages.length > 0 || isBusy ? (
              <>
                {/* Agent action steps */}
                {agentSteps.length > 0 && <AgentSteps steps={agentSteps} />}

                {/* Live thinking — reuses Reasoning card style */}
                {isBusy && thinkingContent.length > 0 && streamingContent.length === 0 && (
                  <LiveThinkingCard content={thinkingContent} Colors={Colors} />
                )}

                {/* Streaming AI response */}
                {isStreaming && streamingContent.length > 0 && (
                  <ChatBubble content={streamingContent} isUser={false} />
                )}

                {/* Typing indicator when busy but not yet streaming */}
                {isBusy && !isStreaming && thinkingContent.length === 0 && <TypingIndicator />}

                {/* Disclaimer after response */}
                {disclaimer && !isBusy && (
                  <Animated.Text
                    entering={enterFade(300)}
                    style={{
                      fontSize: FontSize.xs,
                      color: Colors.textMuted,
                      textAlign: 'center',
                      marginTop: Spacing.md,
                    }}
                  >
                    {disclaimer}
                  </Animated.Text>
                )}
              </>
            ) : null
          }
        />

        {sendError && (
          <ErrorBanner error={sendError} onDismiss={onDismissError} />
        )}

        <ChatInput
          value={input}
          onChangeText={onChangeText}
          onSend={onSend}
          isBusy={isBusy}
          onAttach={onAttach}
          attachment={pendingAttachment}
          onRemoveAttachment={onRemoveAttachment}
          placeholder={placeholder}
        />
    </KeyboardAvoidingView>
  );
}

/** Live thinking card — grows as thoughts stream in, matches persisted ThinkingPartView. */
function LiveThinkingCard({ content, Colors }: { content: string; Colors: ReturnType<typeof useColors> }) {
  return (
    <Animated.View
      entering={enterSlideUp()}
      style={{
        borderWidth: 1,
        borderColor: Colors.border,
        borderRadius: BorderRadius.sm,
        borderCurve: 'continuous',
        marginBottom: Spacing.xs,
        overflow: 'hidden',
      }}
    >
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.xs,
          padding: Spacing.sm,
          backgroundColor: Colors.surface,
        }}
      >
        <Text style={{ fontSize: 12, width: 16, textAlign: 'center' }}>🧠</Text>
        <Text
          style={{
            fontSize: FontSize.xs,
            color: Colors.primary,
            fontWeight: FontWeight.medium,
            flex: 1,
          }}
          numberOfLines={1}
        >
          Reasoning…
        </Text>
      </View>
      <View style={{ padding: Spacing.sm, backgroundColor: Colors.surfaceSecondary }}>
        <Text
          style={{
            fontSize: FontSize.xs,
            color: Colors.textMuted,
            fontStyle: 'italic',
            lineHeight: 18,
          }}
        >
          {content}
        </Text>
      </View>
    </Animated.View>
  );
}

/** Inline error banner above the input — slide-down + shake entrance, slide-up dismiss. */
function ErrorBanner({ error, onDismiss }: { error: SendError; onDismiss?: () => void }) {
  const Colors = useColors();
  const [countdown, setCountdown] = useState(error.retryAfter ?? 0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  // Shake animation on mount
  const shakeX = useSharedValue(0);
  useEffect(() => {
    shakeX.value = withDelay(
      300,
      withSequence(
        withSpring(3, Springs.snappy),
        withSpring(-3, Springs.snappy),
        withSpring(0, Springs.snappy),
      ),
    );
  }, [shakeX]);
  const shakeStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: shakeX.value }],
  }));

  useEffect(() => {
    if (!error.retryAfter) return;
    setCountdown(error.retryAfter);
    intervalRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [error.retryAfter]);

  // Dismiss when countdown reaches 0
  useEffect(() => {
    if (countdown === 0 && error.retryAfter) onDismissRef.current?.();
  }, [countdown, error.retryAfter]);

  // Auto-dismiss non-countdown errors after 5s
  useEffect(() => {
    if (error.retryAfter) return;
    const t = setTimeout(() => onDismissRef.current?.(), 5000);
    return () => clearTimeout(t);
  }, [error.retryAfter]);

  const handleDismiss = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    onDismiss?.();
  }, [onDismiss]);

  return (
    <Animated.View
      entering={enterSlideDown()}
      exiting={SlideOutUp.springify().damping(20)}
      style={[
        shakeStyle,
        {
          flexDirection: 'row',
          alignItems: 'center',
          marginHorizontal: Spacing.md,
          marginBottom: Spacing.sm,
          paddingHorizontal: Spacing.md,
          paddingVertical: Spacing.sm,
          backgroundColor: Colors.errorLight,
          borderRadius: BorderRadius.lg,
          borderCurve: 'continuous',
          gap: Spacing.sm,
        },
      ]}
    >
      <Icon name="alert-circle" size={20} color={Colors.error} />
      <View style={{ flex: 1 }}>
        <Text
          style={{
            fontSize: FontSize.sm,
            color: Colors.error,
            fontWeight: FontWeight.semibold,
          }}
        >
          {error.message}
        </Text>
        {countdown > 0 && (
          <Text
            style={{
              fontSize: FontSize.xs,
              color: Colors.error,
              marginTop: 2,
              opacity: 0.8,
            }}
          >
            Try again in {countdown}s
          </Text>
        )}
      </View>
      <Pressable onPress={handleDismiss} hitSlop={{ top: 14, bottom: 14, left: 14, right: 14 }}>
        <Icon name="close" size={16} color={Colors.error} />
      </Pressable>
    </Animated.View>
  );
}
