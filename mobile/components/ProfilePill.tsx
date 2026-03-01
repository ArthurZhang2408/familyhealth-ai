import { Text, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { Icon } from '@/components/Icon';
import { useProfileStore } from '@/stores/profile';
import { useColors } from '@/hooks/useColors';
import { useHapticPress } from '@/hooks/useHapticPress';
import { useHeaderScale } from '@/hooks/useHeaderScale';
import { FontWeight, Spacing, BorderRadius } from '@/constants/theme';

export function ProfilePill() {
  const Colors = useColors();
  const router = useRouter();
  const header = useHeaderScale();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const handlePress = useHapticPress(() => router.push('/profile-picker'));

  const label = activeProfile?.name ?? 'Select profile';
  const textColor = activeProfile ? Colors.text : Colors.textSecondary;

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: Spacing.xs,
        height: header.buttonSize,
        paddingHorizontal: Spacing.sm,
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous',
        opacity: pressed ? 0.6 : 1,
      })}
    >
      <Text
        style={{
          fontSize: header.titleSize,
          fontWeight: activeProfile ? FontWeight.semibold : FontWeight.medium,
          color: textColor,
        }}
        numberOfLines={1}
      >
        {label}
      </Text>
      <Icon name="chevron-down" size={header.accessorySize} color={Colors.textMuted} />
    </Pressable>
  );
}
