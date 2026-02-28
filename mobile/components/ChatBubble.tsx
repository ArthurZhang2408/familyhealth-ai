import { View, Text } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, BorderRadius } from '@/constants/theme';

interface Props {
  content: string;
  isUser: boolean;
  /** Only animate entrance for newly sent messages, not historical ones */
  animate?: boolean;
}

export function ChatBubble({ content, isUser, animate }: Props) {
  const Colors = useColors();

  const bubble = (
    <View
      style={{
        backgroundColor: isUser ? Colors.primary : Colors.surface,
        borderRadius: BorderRadius.lg,
        borderBottomRightRadius: isUser ? BorderRadius.sm : BorderRadius.lg,
        borderBottomLeftRadius: isUser ? BorderRadius.lg : BorderRadius.sm,
        borderCurve: 'continuous',
        padding: Spacing.md,
        maxWidth: '80%',
        borderWidth: isUser ? 0 : 1,
        borderColor: Colors.border,
      }}
    >
      <Text
        style={{
          fontSize: FontSize.md,
          color: isUser ? Colors.textInverse : Colors.text,
          lineHeight: 22,
        }}
        selectable
      >
        {content}
      </Text>
    </View>
  );

  if (animate) {
    return (
      <Animated.View
        entering={FadeInUp.duration(250).springify().damping(20)}
        style={{ alignItems: isUser ? 'flex-end' : 'flex-start' }}
      >
        {bubble}
      </Animated.View>
    );
  }

  return (
    <View style={{ alignItems: isUser ? 'flex-end' : 'flex-start' }}>
      {bubble}
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
