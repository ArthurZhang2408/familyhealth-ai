import { View, Text } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import Markdown from '@ronradtke/react-native-markdown-display';
import { useColors } from '@/hooks/useColors';
import { useMarkdownStyles } from '@/hooks/useMarkdownStyles';
import { Spacing, FontSize, BorderRadius } from '@/constants/theme';

interface Props {
  content: string;
  isUser: boolean;
  /** Only animate entrance for newly sent messages, not historical ones */
  animate?: boolean;
}

export function ChatBubble({ content, isUser, animate }: Props) {
  const Colors = useColors();
  const markdownStyles = useMarkdownStyles();

  const inner = isUser ? (
    <View
      style={{
        backgroundColor: Colors.surfaceSecondary,
        borderRadius: BorderRadius.lg,
        borderBottomRightRadius: BorderRadius.sm,
        borderCurve: 'continuous',
        padding: Spacing.md,
        maxWidth: '75%',
        marginTop: Spacing.sm,
      }}
    >
      <Text
        style={{
          fontSize: FontSize.md,
          color: Colors.text,
          lineHeight: 22,
        }}
        selectable
      >
        {content}
      </Text>
    </View>
  ) : (
    <View style={{ width: '100%', paddingVertical: Spacing.xs }}>
      <Markdown style={markdownStyles}>{content}</Markdown>
    </View>
  );

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
