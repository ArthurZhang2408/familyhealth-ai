import React from 'react';
import { View, Text } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import Markdown from '@ronradtke/react-native-markdown-display';
import { useColors } from '@/hooks/useColors';
import { useMarkdownStyles } from '@/hooks/useMarkdownStyles';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import {
  AgentStepsPartView,
  MemoryContextPartView,
  StructuredInputView,
  ToolCallPartView,
  ImagePartView,
  ThinkingPartView,
} from '@/components/message-parts';
import type { MessagePart } from '@/types/api';

class PartErrorBoundary extends React.Component<{ fallback: React.ReactNode; children: React.ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  render() { return this.state.hasError ? this.props.fallback : this.props.children; }
}

interface Props {
  content: string;
  contentParts?: MessagePart[];
  isUser: boolean;
  animate?: boolean;
  onStructuredResponse?: (content: string, structuredResponse: Record<string, unknown>) => void;
  isLatestAssistant?: boolean;
}

export function ChatBubble({ content, contentParts, isUser, animate, onStructuredResponse, isLatestAssistant }: Props) {
  const Colors = useColors();
  const markdownStyles = useMarkdownStyles();

  const inner = isUser
    ? <UserBubble content={content} contentParts={contentParts} Colors={Colors} />
    : <AssistantBubble content={content} contentParts={contentParts} Colors={Colors} markdownStyles={markdownStyles} onStructuredResponse={onStructuredResponse} isLatestAssistant={isLatestAssistant} />;

  if (animate) {
    return (
      <Animated.View
        entering={FadeInUp.duration(250).springify().damping(20)}
        style={{ alignItems: isUser ? 'flex-end' : 'flex-start' }}
      >
        {inner}
      </Animated.View>
    );
  }

  return (
    <View style={{ alignItems: isUser ? 'flex-end' : 'flex-start' }}>
      {inner}
    </View>
  );
}

function UserBubble({ content, contentParts, Colors }: { content: string; contentParts?: MessagePart[]; Colors: any }) {
  const images = contentParts?.filter((p): p is Extract<MessagePart, { type: 'image' }> => p.type === 'image');
  const hasText = content.trim().length > 0;

  return (
    <View style={{ alignItems: 'flex-end', maxWidth: '75%', gap: Spacing.xs, marginTop: Spacing.sm }}>
      {images && images.length > 0 && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'flex-end', gap: Spacing.xs }}>
          {images.map((img, i) => <ImagePartView key={i} part={img} />)}
        </View>
      )}
      {hasText && (
        <View
          style={{
            backgroundColor: Colors.surfaceSecondary,
            borderRadius: BorderRadius.lg,
            borderBottomRightRadius: BorderRadius.sm,
            borderCurve: 'continuous',
            padding: Spacing.md,
          }}
        >
          <Text
            style={{ fontSize: FontSize.md, color: Colors.text, lineHeight: 22 }}
            selectable
          >
            {content}
          </Text>
        </View>
      )}
    </View>
  );
}

function AssistantBubble({ content, contentParts, Colors, markdownStyles, onStructuredResponse, isLatestAssistant }: { content: string; contentParts?: MessagePart[]; Colors: any; markdownStyles: any; onStructuredResponse?: Props['onStructuredResponse']; isLatestAssistant?: boolean }) {
  if (!contentParts || contentParts.length === 0) {
    return (
      <View style={{ width: '100%', paddingVertical: Spacing.xs }}>
        <Markdown style={markdownStyles}>{content}</Markdown>
      </View>
    );
  }

  const toolResults = new Map<string, Extract<MessagePart, { type: 'tool_result' }>>();
  for (const p of contentParts) {
    if (p.type === 'tool_result') {
      toolResults.set(p.call_id, p);
    }
  }

  return (
    <PartErrorBoundary fallback={
      <View style={{ width: '100%', paddingVertical: Spacing.xs }}>
        <Markdown style={markdownStyles}>{content}</Markdown>
      </View>
    }>
      <View style={{ width: '100%', paddingVertical: Spacing.xs }}>
        {contentParts.map((part, i) => {
          switch (part.type) {
            case 'thinking':
              return <ThinkingPartView key={i} part={part} />;
            case 'agent_steps':
              return <AgentStepsPartView key={i} part={part} />;
            case 'memory_context':
              return <MemoryContextPartView key={i} part={part} />;
            case 'tool_call':
              // Skip tools that have dedicated UI (structured input, agent steps)
              if (part.name === 'present_question' || part.name === 'search_patient_memory') return null;
              return <ToolCallPartView key={i} call={part} result={toolResults.get(part.id)} />;
            case 'tool_result':
              return null;
            case 'image':
              return <ImagePartView key={i} part={part} />;
            case 'structured_input':
              return <StructuredInputView key={i} part={part} onResponse={onStructuredResponse} isLatest={!!isLatestAssistant} />;
            case 'text':
              return <Markdown key={i} style={markdownStyles}>{part.text}</Markdown>;
            default:
              return null;
          }
        })}
      </View>
    </PartErrorBoundary>
  );
}

/** Animated dots shown while AI is thinking */
export function TypingIndicator() {
  const Colors = useColors();
  return (
    <Animated.View
      entering={FadeInUp.duration(200)}
      style={{ alignItems: 'flex-start' }}
    >
      <View
        style={{
          backgroundColor: Colors.surface,
          borderRadius: BorderRadius.lg,
          borderBottomLeftRadius: BorderRadius.sm,
          borderCurve: 'continuous',
          paddingHorizontal: Spacing.md,
          paddingVertical: Spacing.sm,
          borderWidth: 1,
          borderColor: Colors.border,
          flexDirection: 'row',
          gap: Spacing.xs,
        }}
      >
        {[0, 1, 2].map((i) => (
          <View
            key={i}
            style={{
              width: 7,
              height: 7,
              borderRadius: 4,
              backgroundColor: Colors.textMuted,
              opacity: 0.4 + i * 0.2,
            }}
          />
        ))}
      </View>
    </Animated.View>
  );
}
