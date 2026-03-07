import { RefObject, useEffect } from 'react';
import { View, Text, Pressable, FlatList, KeyboardAvoidingView } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { ChatBubble, TypingIndicator } from '@/components/ChatBubble';
import { ChatInput } from '@/components/ChatInput';
import { AgentSteps } from '@/components/AgentSteps';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Icon, type IconName } from '@/components/Icon';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { LocalMessage } from '@/hooks/useConversation';
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
  agentSteps?: AgentStep[];
  isStreaming?: boolean;
  onStructuredResponse?: (content: string, structuredResponse: Record<string, unknown>) => void;
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
  agentSteps = [],
  isStreaming = false,
  onStructuredResponse,
}: ConversationViewProps) {
  const Colors = useColors();

  const lastAssistantIndex = allMessages.findLastIndex((m) => m.role === 'assistant');

  // Auto-scroll when streaming content updates
  useEffect(() => {
    if (isStreaming || (isBusy && agentSteps.length > 0)) {
      flatListRef.current?.scrollToEnd({ animated: true });
    }
  }, [streamingContent, agentSteps.length, isStreaming, isBusy, flatListRef]);

  if (isLoading) return <LoadingSpinner />;

  if (error && allMessages.length === 0) {
    return (
      <NoProfileGuard>
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
      </NoProfileGuard>
    );
  }

  return (
    <NoProfileGuard>
      <KeyboardAvoidingView
        style={{ flex: 1, backgroundColor: Colors.background }}
        behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        <FlatList
          ref={flatListRef}
          data={allMessages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{
            padding: Spacing.md,
            gap: Spacing.sm,
            flexGrow: 1,
            justifyContent: allMessages.length === 0 ? 'center' : 'flex-start',
          }}
          contentInsetAdjustmentBehavior="automatic"
          renderItem={({ item, index }) => {
            const isLatestAssistant = item.role === 'assistant' && index === lastAssistantIndex;
            return (
              <ChatBubble
                content={item.content}
                contentParts={item.contentParts}
                isUser={item.role === 'user'}
                animate={pendingIds.has(item.id)}
                onStructuredResponse={onStructuredResponse}
                isLatestAssistant={isLatestAssistant}
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
          ListFooterComponent={
            allMessages.length > 0 || isBusy ? (
              <>
                {/* Agent action steps */}
                {agentSteps.length > 0 && <AgentSteps steps={agentSteps} />}

                {/* Streaming AI response */}
                {isStreaming && streamingContent.length > 0 && (
                  <ChatBubble content={streamingContent} isUser={false} />
                )}

                {/* Typing indicator when busy but not yet streaming */}
                {isBusy && !isStreaming && agentSteps.length === 0 && <TypingIndicator />}

                {/* Disclaimer after response */}
                {disclaimer && !isBusy && (
                  <Animated.Text
                    entering={FadeIn.duration(300)}
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
          onLayout={() => {
            if (allMessages.length > 0) flatListRef.current?.scrollToEnd({ animated: false });
          }}
        />

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
    </NoProfileGuard>
  );
}
