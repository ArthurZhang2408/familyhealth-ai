import { useWindowDimensions } from 'react-native';

/**
 * Dynamic header sizing that respects system font scale and screen width.
 * Mirrors the sidebar's `useDynamicFonts()` approach for the header bar.
 *
 * All header elements (buttons, icons, text) derive from this single hook
 * so changing font scale or rotating the device updates everything in lockstep.
 */
export function useHeaderScale() {
  const { fontScale, width } = useWindowDimensions();

  // Base button diameter adapts to screen width
  const base = width < 375 ? 34 : 38;

  // Dampen font scale growth for touch targets (grow, but not as aggressively as text)
  const scale = 1 + (fontScale - 1) * 0.5;

  const buttonSize = Math.round(base * scale);

  return {
    /** Diameter of circular header buttons */
    buttonSize,
    /** Primary icon size inside buttons */
    iconSize: Math.round(buttonSize * 0.53),
    /** Small accessory icon (chevrons) */
    accessorySize: Math.round(buttonSize * 0.33),
    /** Font size for header title / profile name */
    titleSize: Math.round(buttonSize * 0.44),
  };
}
