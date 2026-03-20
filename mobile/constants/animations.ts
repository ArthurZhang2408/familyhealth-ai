import { AccessibilityInfo } from 'react-native';
import {
  withSpring,
  withTiming,
  Easing,
  FadeIn,
  FadeInUp,
  FadeInDown,
  FadeOut,
  type WithSpringConfig,
  type WithTimingConfig,
} from 'react-native-reanimated';

// ── Reduced motion gate ────────────────────────────────────────────────────

let _isReduceMotion = false;
AccessibilityInfo.isReduceMotionEnabled().then((v) => {
  _isReduceMotion = v;
});
AccessibilityInfo.addEventListener('reduceMotionChanged', (v) => {
  _isReduceMotion = v;
});

export const isReduceMotion = () => _isReduceMotion;

// ── Types ──────────────────────────────────────────────────────────────────

export type SpringPreset = WithSpringConfig;
export type TimingPreset = WithTimingConfig;

// ── Spring presets ─────────────────────────────────────────────────────────

export const Springs = {
  /** Buttons, toggles, small UI (< 100px movement) */
  snappy: { damping: 20, stiffness: 300, mass: 0.8 } as SpringPreset,
  /** Screen content, card reveals, larger elements */
  gentle: { damping: 15, stiffness: 150, mass: 1 } as SpringPreset,
  /** Notifications, toasts, attention-drawing */
  bouncy: { damping: 12, stiffness: 200, mass: 0.9 } as SpringPreset,
  /** Sheets, large panels, dropdown */
  heavy: { damping: 20, stiffness: 120, mass: 1.2 } as SpringPreset,
  /** Drag-release, velocity-sensitive */
  interactive: { damping: 15, stiffness: 200, mass: 0.5 } as SpringPreset,
} as const;

// ── Timing presets (opacity/color/progress — never overshoot) ──────────────

export const Timings = {
  /** Opacity entrances */
  fadeIn: { duration: 200, easing: Easing.out(Easing.ease) } as TimingPreset,
  /** Opacity exits */
  fadeOut: { duration: 150, easing: Easing.in(Easing.ease) } as TimingPreset,
  /** Background/border color changes */
  colorShift: { duration: 200, easing: Easing.inOut(Easing.ease) } as TimingPreset,
} as const;

// ── Clamped spring helper ──────────────────────────────────────────────────

/** Returns spring config with overshootClamping: true. Use when spring drives 0-1 progress. */
export function clampedSpring(preset: SpringPreset): SpringPreset {
  return { ...preset, overshootClamping: true };
}

// ── Layout animation factories ─────────────────────────────────────────────

/** Slide up + fade in with snappy spring. Degrades to fade-only under reduce motion. */
export function enterSlideUp(delay?: number) {
  if (_isReduceMotion) {
    const anim = FadeIn.duration(200);
    return delay ? anim.delay(delay) : anim;
  }
  const anim = FadeInUp.springify().damping(20).stiffness(300).mass(0.8);
  return delay ? anim.delay(delay) : anim;
}

/** Slide down + fade in with snappy spring. Degrades to fade-only under reduce motion. */
export function enterSlideDown(delay?: number) {
  if (_isReduceMotion) {
    const anim = FadeIn.duration(200);
    return delay ? anim.delay(delay) : anim;
  }
  const anim = FadeInDown.springify().damping(20).stiffness(300).mass(0.8);
  return delay ? anim.delay(delay) : anim;
}

/** Opacity-only entrance (timing, not spring). */
export function enterFade(delay?: number) {
  const anim = FadeIn.duration(200);
  return delay ? anim.delay(delay) : anim;
}

/** Opacity-only exit (timing). */
export function exitFade() {
  return FadeOut.duration(150);
}

/** Bouncy slide up. Degrades to fade-only under reduce motion. */
export function enterBounce(delay?: number) {
  if (_isReduceMotion) {
    const anim = FadeIn.duration(200);
    return delay ? anim.delay(delay) : anim;
  }
  const anim = FadeInUp.springify().damping(12).stiffness(200).mass(0.9);
  return delay ? anim.delay(delay) : anim;
}

/** Unified 30ms stagger delay for list items. */
export function staggerDelay(index: number) {
  return index * 30;
}
