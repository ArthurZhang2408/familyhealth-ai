/**
 * Animated Salk app icon — SVG recreation of icon.png with two independent animations:
 *
 * **Background (perpetual):** Gradient direction rotates continuously (16s cycle).
 *
 * **Elements:** All five circles + cross start at the viewBox center (60, 60) then
 * spring to their final positions. Single `progress` value (0→1) drives everything
 * via staggered `interpolate` ranges. Center circle has multi-point spring curves
 * for both scale and position. Entrance uses withSpring; loop uses timing-based cycle.
 */
import { useCallback, useEffect, useId } from 'react';
import Svg, { Defs, LinearGradient, Stop, Rect, Circle, Path } from 'react-native-svg';
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withSequence,
  withRepeat,
  withTiming,
  withSpring,
  withDelay,
  interpolate,
  Extrapolation,
  Easing,
  type WithSpringConfig,
} from 'react-native-reanimated';
import { useFocusEffect } from '@react-navigation/native';
import { isReduceMotion } from '@/constants/animations';
import { useColors } from '@/hooks/useColors';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);
const AnimatedRect = Animated.createAnimatedComponent(Rect);
const AnimatedLinearGradient = Animated.createAnimatedComponent(LinearGradient);

// ── ViewBox 120×120 ──────────────────────────────────────────────────
const CX = 60;        // center circle final x
const CY = 52;        // center circle final y
const OY = 60;        // animation origin y (viewBox center)

// Final positions of the four outer circles
const BIG_L = { cx: 48, cy: 68, r: 16, opacity: 0.4 };
const BIG_R = { cx: 72, cy: 68, r: 16, opacity: 0.4 };
const SM_L = { cx: 42, cy: 56, r: 10, opacity: 0.3 };
const SM_R = { cx: 78, cy: 56, r: 10, opacity: 0.3 };

const MAX_SCALE = 1.5;

// ── Loop timing (ms) ─────────────────────────────────────────────────
const HOLD_BIG = 1200;
const EXPAND = 2000;
const HOLD_SETTLED = 3000;
const COLLAPSE = 2000;

// ── Spring dynamics ──────────────────────────────────────────────────
const BOUNCE = 0.07;
const BOUNCE_DECAY = 0.55;
const GROWTH_BOUNCE = 0.06;

// Entrance spring for progress (0→1)
const ENTRANCE_SPRING: WithSpringConfig = { damping: 13, stiffness: 38, mass: 1.5 };

// Center scale: multi-point spring curve (fast drop → undershoot → overshoot → settle)
const CENTER_P = [-0.1, 0, 0.22, 0.36, 0.46, 0.55] as const;
const CENTER_S = [
  MAX_SCALE * (1 + GROWTH_BOUNCE),
  MAX_SCALE,
  1 - BOUNCE,
  1 + BOUNCE * BOUNCE_DECAY,
  1 - BOUNCE * BOUNCE_DECAY ** 2,
  1,
] as const;

// Outer circle stagger ranges (wider = slower dispatch, higher start = more gap)
const BIG_RANGE = [0.4, 0.88] as const;
const SMALL_RANGE = [0.55, 0.98] as const;

// ── Background gradient constants ────────────────────────────────────
const BG_CYCLE_MS = 16000;
const BG_LEN = 85;
const BG_BASE_ANGLE = Math.PI / 4;

interface AnimatedSalkIconProps {
  size?: number;
  showBackground?: boolean;
  loop?: boolean;
  /** Freeze at the initial state (big plus circle only, no animation). */
  static?: boolean;
}

export function AnimatedSalkIcon({ size = 56, showBackground = true, loop = false, static: isStatic = false }: AnimatedSalkIconProps) {
  const Colors = useColors();
  const uid = useId();
  const bgId = `salkBg-${uid}`;
  const bgLightId = `salkBgLight-${uid}`;
  const circleFill = showBackground ? 'white' : Colors.primary;
  const crossFill = showBackground ? '#2563EB' : Colors.background;

  // ── Background gradient — perpetual rotation ───────────────────────
  const bgProgress = useSharedValue(0);

  useEffect(() => {
    if (isStatic || !showBackground || isReduceMotion()) return;
    bgProgress.value = withRepeat(
      withTiming(1, { duration: BG_CYCLE_MS, easing: Easing.linear }),
      -1,
      false,
    );
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const bgAP = useAnimatedProps(() => {
    const angle = bgProgress.value * 2 * Math.PI + BG_BASE_ANGLE;
    return {
      x1: 60 - BG_LEN * Math.cos(angle),
      y1: 60 - BG_LEN * Math.sin(angle),
      x2: 60 + BG_LEN * Math.cos(angle),
      y2: 60 + BG_LEN * Math.sin(angle),
    };
  });

  // ── Element animation ──────────────────────────────────────────────
  const progress = useSharedValue(0);

  useFocusEffect(
    useCallback(() => {
      if (isStatic) return; // frozen at progress=0

      if (isReduceMotion()) {
        progress.value = 1;
        return;
      }

      progress.value = 0;

      if (loop) {
        progress.value = withRepeat(
          withSequence(
            withTiming(0, { duration: HOLD_BIG }),
            withTiming(1, { duration: EXPAND, easing: Easing.out(Easing.quad) }),
            withTiming(1, { duration: HOLD_SETTLED }),
            withTiming(0, { duration: COLLAPSE, easing: Easing.out(Easing.back(1.7)) }),
          ),
          -1,
          false,
        );
      } else {
        // Spring entrance: hold then spring to settled
        progress.value = withDelay(HOLD_BIG, withSpring(1, ENTRANCE_SPRING));
      }

      return () => { progress.value = 0; };
    }, []), // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ── Animated props ─────────────────────────────────────────────────
  // Position is derived from scale: cy arrives at CY the instant scale first
  // reaches 1.0, then stays put while scale does its spring bounces in-place.

  const centerAP = useAnimatedProps(() => {
    const s = interpolate(progress.value, [...CENTER_P], [...CENTER_S], Extrapolation.CLAMP);
    const posP = interpolate(s, [MAX_SCALE, 1], [0, 1], Extrapolation.CLAMP);
    return { r: 20 * s, cy: OY + (CY - OY) * posP };
  });

  const crossVAP = useAnimatedProps(() => {
    const s = interpolate(progress.value, [...CENTER_P], [...CENTER_S], Extrapolation.CLAMP);
    const posP = interpolate(s, [MAX_SCALE, 1], [0, 1], Extrapolation.CLAMP);
    const cy = OY + (CY - OY) * posP;
    return { x: CX - 2 * s, y: cy - 8 * s, width: 4 * s, height: 16 * s };
  });

  const crossHAP = useAnimatedProps(() => {
    const s = interpolate(progress.value, [...CENTER_P], [...CENTER_S], Extrapolation.CLAMP);
    const posP = interpolate(s, [MAX_SCALE, 1], [0, 1], Extrapolation.CLAMP);
    const cy = OY + (CY - OY) * posP;
    return { x: CX - 8 * s, y: cy - 2 * s, width: 16 * s, height: 4 * s };
  });

  // Outer circles: all originate from viewBox center (CX, OY)
  const bigLAP = useAnimatedProps(() => {
    const p = interpolate(progress.value, [...BIG_RANGE], [0, 1], Extrapolation.CLAMP);
    return {
      cx: CX + (BIG_L.cx - CX) * p,
      cy: OY + (BIG_L.cy - OY) * p,
      r: BIG_L.r * p,
      opacity: BIG_L.opacity * p,
    };
  });
  const bigRAP = useAnimatedProps(() => {
    const p = interpolate(progress.value, [...BIG_RANGE], [0, 1], Extrapolation.CLAMP);
    return {
      cx: CX + (BIG_R.cx - CX) * p,
      cy: OY + (BIG_R.cy - OY) * p,
      r: BIG_R.r * p,
      opacity: BIG_R.opacity * p,
    };
  });

  const smLAP = useAnimatedProps(() => {
    const p = interpolate(progress.value, [...SMALL_RANGE], [0, 1], Extrapolation.CLAMP);
    return {
      cx: CX + (SM_L.cx - CX) * p,
      cy: OY + (SM_L.cy - OY) * p,
      r: SM_L.r * p,
      opacity: SM_L.opacity * p,
    };
  });
  const smRAP = useAnimatedProps(() => {
    const p = interpolate(progress.value, [...SMALL_RANGE], [0, 1], Extrapolation.CLAMP);
    return {
      cx: CX + (SM_R.cx - CX) * p,
      cy: OY + (SM_R.cy - OY) * p,
      r: SM_R.r * p,
      opacity: SM_R.opacity * p,
    };
  });

  return (
    <Svg width={size} height={size} viewBox={showBackground ? '0 0 120 120' : isStatic ? '30 30 60 60' : '26 24 68 68'}>
      {showBackground && (
        <>
          <Defs>
            <AnimatedLinearGradient
              id={bgId}
              gradientUnits="userSpaceOnUse"
              animatedProps={bgAP}
            >
              <Stop offset="0%" stopColor="#3B82F6" />
              <Stop offset="50%" stopColor="#2563EB" />
              <Stop offset="100%" stopColor="#10B981" />
            </AnimatedLinearGradient>
            <LinearGradient id={bgLightId} x1="0" y1="0" x2="120" y2="120" gradientUnits="userSpaceOnUse">
              <Stop offset="0%" stopColor="#ffffff" stopOpacity={0.3} />
              <Stop offset="100%" stopColor="#ffffff" stopOpacity={0.1} />
            </LinearGradient>
          </Defs>
          <Rect width={120} height={120} rx={26} fill={`url(#${bgId})`} />
          <Rect width={120} height={120} rx={26} fill={`url(#${bgLightId})`} />
          <Path
            d="M26 0 H94 C108.359 0 120 11.641 120 26 V30 C120 15.641 108.359 4 94 4 H26 C11.641 4 0 15.641 0 30 V26 C0 11.641 11.641 0 26 0 Z"
            fill="white"
            opacity={0.2}
          />
        </>
      )}

      {/* ── Outer circles (behind center) ────────────────────────── */}
      <AnimatedCircle fill={circleFill} animatedProps={bigLAP} />
      <AnimatedCircle fill={circleFill} animatedProps={bigRAP} />

      {/* ── Center circle ────────────────────────────────────────── */}
      <AnimatedCircle cx={CX} fill={circleFill} opacity={0.9} animatedProps={centerAP} />

      {/* ── Medical cross ────────────────────────────────────────── */}
      <AnimatedRect rx={2} fill={crossFill} animatedProps={crossVAP} />
      <AnimatedRect rx={2} fill={crossFill} animatedProps={crossHAP} />

      {/* ── Small accent circles (on top of center) ──────────────── */}
      <AnimatedCircle fill={circleFill} animatedProps={smLAP} />
      <AnimatedCircle fill={circleFill} animatedProps={smRAP} />
    </Svg>
  );
}
