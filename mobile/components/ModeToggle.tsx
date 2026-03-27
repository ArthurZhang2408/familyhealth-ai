import { useEffect } from 'react';
import { Pressable, Text } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withDelay,
  withTiming,
} from 'react-native-reanimated';
import { Icon } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { useHapticPress } from '@/hooks/useHapticPress';
import { useHeaderScale } from '@/hooks/useHeaderScale';
import { FontSize, FontWeight, BorderRadius, Spacing } from '@/constants/theme';
import { Timings } from '@/constants/animations';

export type ConversationMode = 'chat' | 'diagnosis';

interface Props {
  mode: ConversationMode;
  onToggle: () => void;
}

const LABELS: Record<ConversationMode, string> = {
  chat: 'Chat',
  diagnosis: 'Diagnosis',
};

/**
 * Mode toggle with reveal animation: shows text label for ~1s on mode change,
 * then collapses to icon-only. First render also shows the label briefly.
 */
export function ModeToggle({ mode, onToggle }: Props) {
  const Colors = useColors();
  const header = useHeaderScale();
  const handlePress = useHapticPress(onToggle);
  const isChat = mode === 'chat';
  const tint = isChat ? Colors.primary : Colors.accent;

  // 1 = expanded (text visible), 0 = collapsed (icon only)
  const expanded = useSharedValue(1);

  useEffect(() => {
    // On mode change (or first mount): show label, then collapse after 1s
    expanded.value = 1;
    expanded.value = withDelay(1000, withTiming(0, { duration: 300 }));
  }, [mode, expanded]);

  const labelStyle = useAnimatedStyle(() => ({
    opacity: expanded.value,
    maxWidth: expanded.value * 100, // animates from 100 → 0
    overflow: 'hidden' as const,
  }));

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        height: header.buttonSize,
        paddingHorizontal: Spacing.sm,
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous',
        backgroundColor: tint + '15',
        opacity: pressed ? 0.6 : 1,
        gap: 4,
      })}
    >
      <Icon
        name={isChat ? 'chat-fill' : 'stethoscope'}
        size={header.iconSize}
        color={tint}
      />
      <Animated.Text
        style={[
          {
            fontSize: FontSize.xs,
            fontWeight: FontWeight.semibold,
            color: tint,
          },
          labelStyle,
        ]}
        numberOfLines={1}
      >
        {LABELS[mode]}
      </Animated.Text>
    </Pressable>
  );
}
