import { useRef, useCallback, useEffect } from 'react';
import { View, Text, LayoutChangeEvent } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  interpolateColor,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import * as Haptics from 'expo-haptics';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { FontSize, FontWeight, BorderRadius, Spacing } from '@/constants/theme';
import { Springs, isReduceMotion } from '@/constants/animations';

export interface ScaleSliderProps {
  range: { min: number; max: number; step?: number; labels?: { min: string; max: string } };
  value: number | null;
  onValueChange: (value: number) => void;
  interactive: boolean;
}

const TRACK_HEIGHT = 8;
const THUMB_SIZE = 44;
const GHOST_THUMB_SIZE = 28;
const TRACK_PAD = THUMB_SIZE / 2;

function fireHaptic(step: number) {
  if (process.env.EXPO_OS !== 'ios') return;
  const style =
    step <= 3 ? Haptics.ImpactFeedbackStyle.Light
    : step <= 6 ? Haptics.ImpactFeedbackStyle.Medium
    : Haptics.ImpactFeedbackStyle.Heavy;
  Haptics.impactAsync(style);
}

export function ScaleSlider({ range, value, onValueChange, interactive }: ScaleSliderProps) {
  const { min, max } = range;
  const Colors = useColors();
  const shadow = useShadow();
  const trackWidthRef = useRef(0);
  const lastStepRef = useRef<number | null>(null);
  const thumbX = useSharedValue(0);
  const thumbOpacity = useSharedValue(0);
  const normalizedPos = useSharedValue(0);

  const stepToX = useCallback(
    (s: number) => ((s - min) / (max - min)) * trackWidthRef.current,
    [min, max],
  );

  const animateToStep = useCallback((step: number) => {
    const x = stepToX(step);
    const norm = (step - min) / (max - min);
    const reduce = isReduceMotion();
    thumbX.value = reduce ? x : withSpring(x, Springs.snappy);
    normalizedPos.value = reduce ? norm : withSpring(norm, Springs.snappy);
    thumbOpacity.value = 1;
  }, [stepToX, min, max, thumbX, normalizedPos, thumbOpacity]);

  useEffect(() => {
    if (!interactive && value !== null && trackWidthRef.current > 0) {
      thumbX.value = stepToX(value);
      normalizedPos.value = (value - min) / (max - min);
      thumbOpacity.value = 1;
      lastStepRef.current = value;
    }
  }, [interactive, value, min, max, stepToX, thumbX, normalizedPos, thumbOpacity]);

  const handleStep = useCallback((step: number) => {
    if (step !== lastStepRef.current) {
      lastStepRef.current = step;
      fireHaptic(step);
    }
    onValueChange(step);
  }, [onValueChange]);

  const computeStep = useCallback((x: number): number | null => {
    const tw = trackWidthRef.current;
    if (tw === 0) return null;
    const clamped = Math.max(TRACK_PAD, Math.min(x, TRACK_PAD + tw));
    return Math.max(min, Math.min(max, Math.round(((clamped - TRACK_PAD) / tw) * (max - min) + min)));
  }, [min, max]);

  const handleGesture = useCallback((x: number) => {
    const step = computeStep(x);
    if (step === null) return;
    animateToStep(step);
    handleStep(step);
  }, [computeStep, animateToStep, handleStep]);

  const pan = Gesture.Pan()
    .enabled(interactive)
    .runOnJS(true)
    .onBegin((e) => handleGesture(e.x))
    .onUpdate((e) => handleGesture(e.x));

  const onLayout = useCallback((e: LayoutChangeEvent) => {
    trackWidthRef.current = e.nativeEvent.layout.width - TRACK_PAD * 2;
  }, []);

  const colors3 = [Colors.success, Colors.warning, Colors.error] as const;

  const filledTrackStyle = useAnimatedStyle(() => ({
    width: thumbX.value + TRACK_PAD,
    opacity: thumbOpacity.value,
    backgroundColor: interpolateColor(normalizedPos.value, [0, 0.5, 1], [...colors3]),
  }));

  const thumbStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: thumbX.value }],
    opacity: thumbOpacity.value,
    borderColor: interpolateColor(normalizedPos.value, [0, 0.5, 1], [...colors3]),
  }));

  // Ghost thumb: visible at center before first interaction, fades when real thumb appears
  const ghostStyle = useAnimatedStyle(() => ({
    opacity: 1 - thumbOpacity.value,
  }));

  const colorTextStyle = useAnimatedStyle(() => ({
    color: interpolateColor(normalizedPos.value, [0, 0.5, 1], [...colors3]),
  }));

  return (
    <View
      style={[!interactive && { opacity: 0.5 }]}
      pointerEvents={interactive ? 'auto' : 'none'}
      accessibilityRole="adjustable"
      accessibilityValue={{ min, max, now: value ?? min }}
    >
      {value !== null && (
        <Animated.Text
          style={[{ textAlign: 'center', fontSize: FontSize.xl, fontWeight: FontWeight.bold }, colorTextStyle]}
        >
          {value}
        </Animated.Text>
      )}
      <GestureDetector gesture={pan}>
        <View onLayout={onLayout} style={{ height: THUMB_SIZE, justifyContent: 'center' }}>
          <View style={{
            marginHorizontal: TRACK_PAD, height: TRACK_HEIGHT,
            borderRadius: BorderRadius.full, borderCurve: 'continuous', backgroundColor: Colors.surfaceSecondary,
          }} />
          <Animated.View style={[{
            position: 'absolute', left: 0, height: TRACK_HEIGHT,
            borderRadius: BorderRadius.full, borderCurve: 'continuous',
            top: (THUMB_SIZE - TRACK_HEIGHT) / 2,
          }, filledTrackStyle]} />
          {/* Ghost thumb — centered affordance hint before first interaction */}
          {interactive && (
            <Animated.View
              style={[{ position: 'absolute', left: TRACK_PAD, right: TRACK_PAD, height: THUMB_SIZE, justifyContent: 'center', alignItems: 'center' }, ghostStyle]}
              pointerEvents="none"
            >
              <View style={[{
                width: GHOST_THUMB_SIZE, height: GHOST_THUMB_SIZE,
                borderRadius: GHOST_THUMB_SIZE / 2, borderCurve: 'continuous',
                backgroundColor: Colors.surface, borderWidth: 2, borderColor: Colors.border,
              }, shadow.md]} />
            </Animated.View>
          )}
          {/* Real thumb — appears on first tap/drag */}
          <Animated.View style={[{
            position: 'absolute', width: THUMB_SIZE, height: THUMB_SIZE,
            borderRadius: THUMB_SIZE / 2, borderCurve: 'continuous',
            backgroundColor: Colors.surface, borderWidth: 2,
            alignItems: 'center', justifyContent: 'center',
          }, shadow.md, thumbStyle]}>
            <Animated.Text style={[{ fontSize: FontSize.sm, fontWeight: FontWeight.bold }, colorTextStyle]}>
              {value ?? ''}
            </Animated.Text>
          </Animated.View>
        </View>
      </GestureDetector>
      {range.labels && (
        <View style={{
          flexDirection: 'row', justifyContent: 'space-between',
          paddingHorizontal: TRACK_PAD, marginTop: Spacing.xs,
        }}>
          <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>{range.labels.min}</Text>
          <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>{range.labels.max}</Text>
        </View>
      )}
    </View>
  );
}
