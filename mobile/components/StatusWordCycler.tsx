import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withRepeat,
  Easing,
} from 'react-native-reanimated';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight } from '@/constants/theme';
import { isReduceMotion } from '@/constants/animations';

interface StatusWordCyclerProps {
  words: string[];
  intervalMs?: number;
  slowPulse?: boolean;
}

const FADE_MS = 120;
const DOT_SIZE = 6;

/**
 * Single-text fade: fade out → swap text → fade in.
 * No overlapping texts, no alignment issues.
 */
export function StatusWordCycler({
  words,
  intervalMs = 1800,
  slowPulse = false,
}: StatusWordCyclerProps) {
  const colors = useColors();
  const reduced = isReduceMotion();
  const [text, setText] = useState(words[0] ?? '');
  const textOpacity = useSharedValue(1);
  const dotOpacity = useSharedValue(reduced ? 0.8 : 0.3);
  const aliveRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const wordsKey = words.join('\0');

  useEffect(() => {
    aliveRef.current = true;
    let idx = 0;

    // Fade out, swap, fade in
    const swapTo = (word: string, then?: () => void) => {
      if (!aliveRef.current) return;
      if (reduced) {
        setText(word);
        then?.();
        return;
      }
      // Fade out
      textOpacity.value = withTiming(0, { duration: FADE_MS, easing: Easing.out(Easing.ease) });
      timerRef.current = setTimeout(() => {
        if (!aliveRef.current) return;
        setText(word);
        // Fade in
        textOpacity.value = withTiming(1, { duration: FADE_MS, easing: Easing.in(Easing.ease) });
        timerRef.current = setTimeout(() => {
          if (!aliveRef.current) return;
          then?.();
        }, FADE_MS);
      }, FADE_MS);
    };

    const tick = () => {
      timerRef.current = setTimeout(() => {
        if (!aliveRef.current) return;
        idx = (idx + 1) % words.length;
        swapTo(words[idx], words.length > 1 ? tick : undefined);
      }, intervalMs);
    };

    // Transition to first word, then start cycling
    swapTo(words[0], words.length > 1 ? tick : undefined);

    return () => {
      aliveRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      textOpacity.value = 1;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wordsKey, intervalMs, reduced]);

  // Dot pulse
  useEffect(() => {
    if (reduced) {
      dotOpacity.value = 0.8;
      return;
    }
    dotOpacity.value = 0.3;
    dotOpacity.value = withRepeat(
      withTiming(0.8, { duration: slowPulse ? 3000 : 1000 }),
      -1,
      true,
    );
  }, [slowPulse, reduced, dotOpacity]);

  const textStyle = useAnimatedStyle(() => ({ opacity: textOpacity.value }));
  const dotStyle = useAnimatedStyle(() => ({ opacity: dotOpacity.value }));

  if (words.length === 0) return null;

  return (
    <View
      style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, flex: 1 }}
      accessibilityLabel="AI is processing your request"
      accessibilityRole="text"
    >
      <Animated.View
        style={[
          {
            width: DOT_SIZE,
            height: DOT_SIZE,
            borderRadius: DOT_SIZE / 2,
            backgroundColor: colors.primary,
          },
          dotStyle,
        ]}
      />
      <Animated.Text
        style={[
          { color: colors.textSecondary, fontSize: FontSize.sm, fontWeight: FontWeight.medium },
          textStyle,
        ]}
        numberOfLines={1}
      >
        {text}
      </Animated.Text>
    </View>
  );
}
