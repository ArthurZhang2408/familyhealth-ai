import { Pressable } from 'react-native';
import { Icon, type IconName } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { useHapticPress } from '@/hooks/useHapticPress';
import { useHeaderScale } from '@/hooks/useHeaderScale';
import { BorderRadius } from '@/constants/theme';

interface Props {
  icon: IconName;
  onPress: () => void;
  /** Tint color for icon + translucent background. Omit for neutral (surfaceSecondary + text). */
  tint?: string;
}

/**
 * Consistent circular icon button for the navigation header.
 * Size scales dynamically via useHeaderScale() — respects font scale + screen width.
 */
export function HeaderIconButton({ icon, onPress, tint }: Props) {
  const Colors = useColors();
  const header = useHeaderScale();
  const handlePress = useHapticPress(onPress);

  const bg = tint ? tint + '15' : Colors.surfaceSecondary;
  const fg = tint ?? Colors.text;

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => ({
        width: header.buttonSize,
        height: header.buttonSize,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous',
        backgroundColor: bg,
        opacity: pressed ? 0.6 : 1,
      })}
    >
      <Icon name={icon} size={header.iconSize} color={fg} />
    </Pressable>
  );
}
