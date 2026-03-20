import React, { useEffect } from 'react';
import { View, Text, Pressable } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withRepeat,
  withSequence,
  withTiming,
  withDelay,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import Markdown from '@ronradtke/react-native-markdown-display';
import { useColors } from '@/hooks/useColors';
import { useMarkdownStyles } from '@/hooks/useMarkdownStyles';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { enterSlideUp, Springs } from '@/constants/animations';
import {
  AgentStepsPartView,
  MemoryContextPartView,
  StructuredInputView,
  ToolCallPartView,
  ImagePartView,
  ThinkingPartView,
} from '@/components/message-parts';
import { DiagnosisReportView } from '@/components/message-parts/DiagnosisReportView';
import type { MessagePart } from '@/types/api';
import { stripThinkingTags } from '@/utils/stripThinking';

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
  sendErrorCount?: number;
}

export function ChatBubble({ content, contentParts, isUser, animate, onStructuredResponse, isLatestAssistant, sendErrorCount }: Props) {
  const Colors = useColors();
  const markdownStyles = useMarkdownStyles();
  const scale = useSharedValue(1);

  const inner = isUser
    ? <UserBubble content={content} contentParts={contentParts} Colors={Colors} />
    : <AssistantBubble content={content} contentParts={contentParts} Colors={Colors} markdownStyles={markdownStyles} onStructuredResponse={onStructuredResponse} isLatestAssistant={isLatestAssistant} sendErrorCount={sendErrorCount} />;

  // Long-press squeeze — only on static (non-entering, non-streaming) messages
  const enableSqueeze = !animate;
  const scaleStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handleLongPress = () => {
    if (!enableSqueeze) return;
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    scale.value = withSpring(0.97, Springs.snappy);
  };
  const handlePressOut = () => {
    if (!enableSqueeze) return;
    scale.value = withSpring(1, Springs.snappy);
  };

  if (animate) {
    return (
      <Animated.View
        entering={enterSlideUp()}
        style={{ alignItems: isUser ? 'flex-end' : 'flex-start' }}
      >
        {inner}
      </Animated.View>
    );
  }

  return (
    <Pressable
      onLongPress={handleLongPress}
      onPressOut={handlePressOut}
      delayLongPress={300}
    >
      <Animated.View style={[{ alignItems: isUser ? 'flex-end' : 'flex-start' }, scaleStyle]}>
        {inner}
      </Animated.View>
    </Pressable>
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

function AssistantBubble({ content, contentParts, Colors, markdownStyles, onStructuredResponse, isLatestAssistant, sendErrorCount = 0 }: { content: string; contentParts?: MessagePart[]; Colors: any; markdownStyles: any; onStructuredResponse?: Props['onStructuredResponse']; isLatestAssistant?: boolean; sendErrorCount?: number }) {
  if (!contentParts || contentParts.length === 0) {
    return (
      <View style={{ width: '100%', paddingVertical: Spacing.xs }}>
        <Markdown style={markdownStyles}>{stripThinkingTags(content)}</Markdown>
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
        <Markdown style={markdownStyles}>{stripThinkingTags(content)}</Markdown>
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
            case 'assessment':
              return <DiagnosisReportView key={i} part={part} />;
            case 'tool_call':
              // Skip tools that have dedicated UI (structured input, agent steps, assessment)
              if (part.name === 'present_question' || part.name === 'present_assessment' || part.name === 'search_patient_memory') return null;
              return <ToolCallPartView key={i} call={part} result={toolResults.get(part.id)} />;
            case 'tool_result':
              return null;
            case 'image':
              return <ImagePartView key={i} part={part} />;
            case 'structured_input':
              return <StructuredInputView key={`si-${part.prompt}-${sendErrorCount}`} part={part} onResponse={onStructuredResponse} isLatest={!!isLatestAssistant} />;
            case 'text':
              return <Markdown key={i} style={markdownStyles}>{stripThinkingTags(part.text)}</Markdown>;
            default:
              return null;
          }
        })}
      </View>
    </PartErrorBoundary>
  );
}

/** Animated dots shown while AI is thinking — pulsing opacity with stagger */
export function TypingIndicator() {
  const Colors = useColors();

  const dot0 = useSharedValue(0.3);
  const dot1 = useSharedValue(0.3);
  const dot2 = useSharedValue(0.3);

  useEffect(() => {
    dot0.value = withRepeat(withSequence(withTiming(0.8, { duration: 400 }), withTiming(0.3, { duration: 400 })), -1, true);
    dot1.value = withDelay(150, withRepeat(withSequence(withTiming(0.8, { duration: 400 }), withTiming(0.3, { duration: 400 })), -1, true));
    dot2.value = withDelay(300, withRepeat(withSequence(withTiming(0.8, { duration: 400 }), withTiming(0.3, { duration: 400 })), -1, true));
  }, [dot0, dot1, dot2]);

  const style0 = useAnimatedStyle(() => ({ opacity: dot0.value }));
  const style1 = useAnimatedStyle(() => ({ opacity: dot1.value }));
  const style2 = useAnimatedStyle(() => ({ opacity: dot2.value }));

  const dotBase = {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: Colors.textMuted,
  };

  return (
    <Animated.View
      entering={enterSlideUp()}
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
        <Animated.View style={[dotBase, style0]} />
        <Animated.View style={[dotBase, style1]} />
        <Animated.View style={[dotBase, style2]} />
      </View>
    </Animated.View>
  );
}
