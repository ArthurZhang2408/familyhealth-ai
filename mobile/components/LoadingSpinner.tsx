import { View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { useColors } from '@/hooks/useColors';
import { Spacing, BorderRadius } from '@/constants/theme';

/** Full-screen themed loading state with skeleton chat bubbles */
export function LoadingSpinner() {
  const Colors = useColors();

  return (
    <Animated.View
      entering={FadeIn.duration(150)}
      style={{
        flex: 1,
        backgroundColor: Colors.background,
        padding: Spacing.md,
        gap: Spacing.md,
        justifyContent: 'flex-end',
        paddingBottom: 100,
      }}
    >
      <SkeletonRow ratio={0.45} align="left" color={Colors.surface} border={Colors.border} />
      <SkeletonRow ratio={0.6} align="right" color={Colors.primary + '20'} />
      <SkeletonRow ratio={0.7} align="left" color={Colors.surface} border={Colors.border} />
      <SkeletonRow ratio={0.4} align="right" color={Colors.primary + '20'} />
      <SkeletonRow ratio={0.55} align="left" color={Colors.surface} border={Colors.border} />
    </Animated.View>
  );
}

function SkeletonRow({
  ratio,
  align,
  color,
  border,
}: {
  ratio: number;
  align: 'left' | 'right';
  color: string;
  border?: string;
}) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
      <View
        style={{
          flex: ratio,
          height: 36,
          borderRadius: BorderRadius.lg,
          borderCurve: 'continuous',
          backgroundColor: color,
          borderWidth: border ? 1 : 0,
          borderColor: border,
          opacity: 0.5,
        }}
      />
      <View style={{ flex: 1 - ratio }} />
    </View>
  );
}
