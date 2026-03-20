import { useEffect } from 'react';
import {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

/** Returns an animated style that pulses opacity between 0.3 and 0.6 (1s cycle). */
export function useShimmer() {
  const opacity = useSharedValue(0.3);

  useEffect(() => {
    opacity.value = withRepeat(withTiming(0.6, { duration: 1000 }), -1, true);
  }, [opacity]);

  const shimmerStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
  }));

  return { shimmerStyle, opacity };
}
