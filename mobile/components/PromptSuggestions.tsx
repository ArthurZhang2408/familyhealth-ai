import { useRef, useCallback, useEffect, type RefObject } from 'react';
import { View, Text, Pressable, ScrollView } from 'react-native';
import Animated, { useSharedValue, useAnimatedStyle, withSpring, withTiming, withSequence } from 'react-native-reanimated';
import { Icon } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { useHapticPress } from '@/hooks/useHapticPress';
import { useShimmer } from '@/hooks/useShimmer';
import { Spacing, FontSize, BorderRadius } from '@/constants/theme';
import { Springs, Timings } from '@/constants/animations';
import type { Suggestion } from '@/services/suggestions';

// ── Public API ──────────────────────────────────────────────────────

export type { Suggestion } from '@/services/suggestions';

/** Pure renderer — accepts suggestions from any source. */
export interface PromptSuggestionsProps {
  suggestions: Suggestion[];
  isLoading?: boolean;
  onSelectPrompt: (text: string) => void;
  onNavigateSession?: (sessionId: string, type: 'chat' | 'diagnosis') => void;
  disabled?: boolean;
}

// ── Internals ───────────────────────────────────────────────────────

function getAccent(c: ReturnType<typeof useColors>, accent: Suggestion['accent']) {
  switch (accent) {
    case 'warning':  return { bg: c.warning + '12', circleBg: c.warning + '20', icon: c.warning };
    case 'success':  return { bg: c.success + '10', circleBg: c.success + '18', icon: c.success };
    case 'primary':  return { bg: c.primary + '08', circleBg: c.primary + '12', icon: c.primary };
    default:         return { bg: c.surface,         circleBg: c.primary + '12', icon: c.primary };
  }
}

function isSessionCard(s: Suggestion) {
  return (s.type === 'continue' || s.type === 'follow_up') && !!s.sessionId;
}

function Chip({ suggestion, onSelectPrompt, onNavigateSession, disabled }: {
  suggestion: Suggestion;
  onSelectPrompt: PromptSuggestionsProps['onSelectPrompt'];
  onNavigateSession?: PromptSuggestionsProps['onNavigateSession'];
  disabled?: boolean;
}) {
  const colors = useColors();
  const accent = getAccent(colors, suggestion.accent);
  const scale = useSharedValue(1);
  const scaleStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  const handlePress = useHapticPress(
    useCallback(() => {
      scale.value = withSequence(
        withSpring(0.96, Springs.snappy),
        withSpring(1, Springs.snappy),
      );
      if (isSessionCard(suggestion) && onNavigateSession) {
        onNavigateSession(suggestion.sessionId!, suggestion.sessionType!);
      } else {
        onSelectPrompt(suggestion.text);
      }
    }, [suggestion, onSelectPrompt, onNavigateSession, scale]),
  );

  return (
    <Pressable onPress={handlePress} disabled={disabled} style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}>
      <Animated.View style={[{
        flexDirection: 'row' as const,
        alignItems: 'center' as const,
        gap: Spacing.xs,
        paddingHorizontal: Spacing.sm + 2,
        paddingVertical: Spacing.sm,
        backgroundColor: accent.bg,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous' as const,
      }, scaleStyle]}>
        <View style={{
          width: 24, height: 24, borderRadius: BorderRadius.full, borderCurve: 'continuous',
          backgroundColor: accent.circleBg, alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name={suggestion.icon} size={13} color={accent.icon} />
        </View>
        <Text numberOfLines={1} style={{ fontSize: FontSize.sm, color: colors.text }}>
          {suggestion.text}
        </Text>
        {isSessionCard(suggestion) && (
          <Icon name="chevron-right" size={12} color={colors.textMuted} />
        )}
      </Animated.View>
    </Pressable>
  );
}

function SkeletonRow() {
  const colors = useColors();
  const { shimmerStyle } = useShimmer();
  const pill = { height: 40, backgroundColor: colors.surfaceSecondary, borderRadius: BorderRadius.full, borderCurve: 'continuous' as const };
  return (
    <View style={{ flexDirection: 'row', gap: Spacing.sm, paddingHorizontal: Spacing.md }}>
      <Animated.View style={[pill, { width: 140 }, shimmerStyle]} />
      <Animated.View style={[pill, { width: 120 }, shimmerStyle]} />
      <Animated.View style={[pill, { width: 100 }, shimmerStyle]} />
    </View>
  );
}

// ── Component ───────────────────────────────────────────────────────

export function PromptSuggestions({
  suggestions,
  isLoading,
  onSelectPrompt,
  onNavigateSession,
  disabled,
}: PromptSuggestionsProps) {
  const listOpacity = useSharedValue(1);
  const prevKey = useRef('');
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const key = suggestions.map((s) => s.id).join(',');
    if (key === prevKey.current) return;
    const isFirst = !prevKey.current;
    prevKey.current = key;
    scrollRef.current?.scrollTo({ x: 0, animated: false });
    if (isFirst) return;
    listOpacity.value = withTiming(0, { duration: 120 });
    const timer = setTimeout(() => { listOpacity.value = withTiming(1, Timings.fadeIn); }, 120);
    return () => clearTimeout(timer);
  }, [suggestions, listOpacity]);

  const listStyle = useAnimatedStyle(() => ({ opacity: listOpacity.value }));

  if (isLoading) return <SkeletonRow />;
  if (suggestions.length === 0) return null;

  return (
    <Animated.View style={listStyle}>
      <ScrollView
        ref={scrollRef}
        horizontal
        showsHorizontalScrollIndicator={false}
        keyboardShouldPersistTaps="always"
        contentContainerStyle={{ gap: Spacing.sm, paddingHorizontal: Spacing.md }}
      >
        {suggestions.map((s) => (
          <Chip key={s.id} suggestion={s}
            onSelectPrompt={onSelectPrompt} onNavigateSession={onNavigateSession} disabled={disabled} />
        ))}
      </ScrollView>
    </Animated.View>
  );
}
