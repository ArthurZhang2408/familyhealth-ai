import { useCallback } from 'react';
import { Pressable } from 'react-native';
import { useFocusEffect } from 'expo-router';
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
import { FontSize, FontWeight, BorderRadius } from '@/constants/theme';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

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
 * Mode toggle with reveal animation: shows text label for ~1s on focus/mode change,
 * then collapses to icon-only. Uses useFocusEffect so Drawer re-triggers on navigation.
 */
export function ModeToggle({ mode, onToggle }: Props) {
  const Colors = useColors();
  const header = useHeaderScale();
  const handlePress = useHapticPress(onToggle);
  const isChat = mode === 'chat';
  const tint = isChat ? Colors.primary : Colors.accent;

  // 1 = expanded (text visible), 0 = collapsed (icon only)
  const expanded = useSharedValue(1);

  useFocusEffect(
    useCallback(() => {
      expanded.value = 1;
      expanded.value = withDelay(1000, withTiming(0, { duration: 300 }));
    }, [mode, expanded]),
  );

  const textStyle = useAnimatedStyle(() => ({
    opacity: expanded.value,
    maxWidth: expanded.value * 80,
    marginLeft: expanded.value * 4,
    overflow: 'hidden' as const,
  }));

  const containerStyle = useAnimatedStyle(() => ({
    paddingLeft: expanded.value * 8,
    paddingRight: expanded.value * 10,
  }));

  return (
    <AnimatedPressable
      onPress={handlePress}
      style={[
        {
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          height: header.buttonSize,
          minWidth: header.buttonSize,
          borderRadius: BorderRadius.full,
          borderCurve: 'continuous',
          backgroundColor: tint + '15',
        },
        containerStyle,
      ]}
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
          textStyle,
        ]}
        numberOfLines={1}
      >
        {LABELS[mode]}
      </Animated.Text>
    </AnimatedPressable>
  );
}
