import { useEffect, useRef } from 'react';
import { View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import { isReduceMotion } from '@/constants/animations';
import { useColors } from '@/hooks/useColors';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

const RING_SIZE = 40;
const RING_STROKE = 4;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const CONFIDENCE_FILL: Record<string, number> = {
  most_likely: 0.82,
  possible: 0.5,
  less_likely: 0.22,
};

export interface ConfidenceRingProps {
  confidence: string;
  color: string;
  delay?: number;
}

export function ConfidenceRing({ confidence, color, delay }: ConfidenceRingProps) {
  const Colors = useColors();
  const progress = useSharedValue(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const targetFill = CONFIDENCE_FILL[confidence] ?? 0;
  const ringColor = targetFill === 0 ? Colors.textMuted : color;

  useEffect(() => {
    if (isReduceMotion()) {
      progress.value = targetFill;
    } else {
      timerRef.current = setTimeout(() => {
        progress.value = withTiming(targetFill, {
          duration: 700,
          easing: Easing.out(Easing.cubic),
        });
      }, delay ?? 0);
    }
    return () => clearTimeout(timerRef.current);
  // Fire once on mount — assessments are immutable, confidence never changes after delivery
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: RING_CIRCUMFERENCE * (1 - progress.value),
  }));

  return (
    <View style={{ width: RING_SIZE, height: RING_SIZE, alignItems: 'center', justifyContent: 'center' }}>
      <Svg
        width={RING_SIZE}
        height={RING_SIZE}
        style={{ position: 'absolute', transform: [{ rotate: '-90deg' }] }}
      >
        <Circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          stroke={ringColor}
          strokeWidth={RING_STROKE}
          fill="none"
          opacity={0.1}
        />
        <AnimatedCircle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RING_RADIUS}
          stroke={ringColor}
          strokeWidth={RING_STROKE}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={RING_CIRCUMFERENCE}
          animatedProps={animatedProps}
        />
      </Svg>
    </View>
  );
}
