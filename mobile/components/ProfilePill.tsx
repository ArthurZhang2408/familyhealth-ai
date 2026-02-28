import { Text, Pressable, View } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { useProfileStore } from '@/stores/profile';
import { useColors } from '@/hooks/useColors';
import { FontSize, FontWeight, Spacing, BorderRadius } from '@/constants/theme';
import type { Relationship } from '@/types/api';
import type { ColorPalette } from '@/constants/colors';

function getRelationshipColors(Colors: ColorPalette): Record<Relationship, string> {
  return {
    self: Colors.relationshipSelf,
    parent: Colors.relationshipParent,
    spouse: Colors.relationshipSpouse,
    child: Colors.relationshipChild,
    sibling: Colors.relationshipSibling,
    other: Colors.relationshipOther,
  };
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

export function ProfilePill() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);

  const handlePress = () => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    router.push('/profile-picker');
  };

  if (!activeProfile) {
    return (
      <Pressable
        onPress={handlePress}
        style={({ pressed }) => ({
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.xs,
          paddingHorizontal: Spacing.sm,
          paddingVertical: Spacing.xs,
          borderRadius: BorderRadius.sm,
          borderCurve: 'continuous',
          opacity: pressed ? 0.6 : 1,
        })}
      >
        <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.medium, color: Colors.textSecondary }}>
          Select profile
        </Text>
        <Icon name="chevron-down" size={12} color={Colors.textMuted} />
      </Pressable>
    );
  }

  const color = getRelationshipColors(Colors)[activeProfile.relationship];

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: Spacing.sm,
        paddingHorizontal: Spacing.sm,
        paddingVertical: Spacing.xs,
        borderRadius: BorderRadius.sm,
        borderCurve: 'continuous',
        opacity: pressed ? 0.6 : 1,
      })}
    >
      <View
        style={{
          width: 26,
          height: 26,
          borderRadius: BorderRadius.full,
          backgroundColor: color + '20',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Text style={{ fontSize: 11, fontWeight: FontWeight.bold, color }}>
          {getInitials(activeProfile.name)}
        </Text>
      </View>
      <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.text }}>
        {activeProfile.name}
      </Text>
      <Icon name="chevron-down" size={12} color={Colors.textMuted} />
    </Pressable>
  );
}
