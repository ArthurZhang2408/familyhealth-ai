import * as Haptics from 'expo-haptics';

/**
 * Returns a callback that fires iOS haptic feedback before calling `onPress`.
 * Use this for any interactive element that should have tactile feedback.
 */
export function useHapticPress(
  onPress: () => void,
  style: Haptics.ImpactFeedbackStyle = Haptics.ImpactFeedbackStyle.Light,
): () => void {
  return () => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(style);
    onPress();
  };
}
