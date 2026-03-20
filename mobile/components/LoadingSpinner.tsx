import { View } from 'react-native';
import Animated from 'react-native-reanimated';
import { useColors } from '@/hooks/useColors';
import { Spacing, BorderRadius } from '@/constants/theme';
import { enterFade } from '@/constants/animations';
import { useShimmer } from '@/hooks/useShimmer';

/** Full-screen themed loading state with skeleton chat bubbles */
export function LoadingSpinner() {
  const Colors = useColors();
  const { shimmerStyle } = useShimmer();

  return (
    <Animated.View
      entering={enterFade()}
      style={{
        flex: 1,
        backgroundColor: Colors.background,
        padding: Spacing.md,
        gap: Spacing.md,
        justifyContent: 'flex-end',
        paddingBottom: 100,
      }}
    >
      <SkeletonRow ratio={0.45} align="left" color={Colors.surface} border={Colors.border} shimmerStyle={shimmerStyle} />
      <SkeletonRow ratio={0.6} align="right" color={Colors.primary + '20'} shimmerStyle={shimmerStyle} />
      <SkeletonRow ratio={0.7} align="left" color={Colors.surface} border={Colors.border} shimmerStyle={shimmerStyle} />
      <SkeletonRow ratio={0.4} align="right" color={Colors.primary + '20'} shimmerStyle={shimmerStyle} />
      <SkeletonRow ratio={0.55} align="left" color={Colors.surface} border={Colors.border} shimmerStyle={shimmerStyle} />
    </Animated.View>
  );
}

function SkeletonRow({
  ratio,
  align,
  color,
  border,
  shimmerStyle,
}: {
  ratio: number;
  align: 'left' | 'right';
  color: string;
  border?: string;
  shimmerStyle: any;
}) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
      <Animated.View
        style={[
          shimmerStyle,
          {
            flex: ratio,
            height: 36,
            borderRadius: BorderRadius.lg,
            borderCurve: 'continuous',
            backgroundColor: color,
            borderWidth: border ? 1 : 0,
            borderColor: border,
          },
        ]}
      />
      <View style={{ flex: 1 - ratio }} />
    </View>
  );
}
