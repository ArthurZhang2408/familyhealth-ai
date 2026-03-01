import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useColors } from '@/hooks/useColors';
import { useHeaderScale } from '@/hooks/useHeaderScale';
import { Spacing } from '@/constants/theme';

interface Props {
  left?: React.ReactNode;
  center?: React.ReactNode;
  right?: React.ReactNode;
}

/**
 * Custom header bar replacing React Navigation's default.
 * Height and slot sizing scale dynamically with useHeaderScale().
 */
export function HeaderBar({ left, center, right }: Props) {
  const Colors = useColors();
  const insets = useSafeAreaInsets();
  const header = useHeaderScale();

  return (
    <View
      style={{
        backgroundColor: Colors.background,
        paddingTop: insets.top,
      }}
    >
      <View
        style={{
          height: header.buttonSize + Spacing.sm * 2,
          flexDirection: 'row',
          alignItems: 'center',
          paddingHorizontal: Spacing.md,
        }}
      >
        {/* Left slot — fixed width so center stays centered */}
        <View style={{ minWidth: header.buttonSize, alignItems: 'flex-start' }}>
          {left}
        </View>

        {/* Center slot — fills remaining space, content centered */}
        <View style={{ flex: 1, alignItems: 'center' }}>
          {center}
        </View>

        {/* Right slot — mirrors left width */}
        <View style={{ minWidth: header.buttonSize, alignItems: 'flex-end' }}>
          {right}
        </View>
      </View>
    </View>
  );
}
