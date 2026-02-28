import { View, Text, Pressable, type ViewStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { Profile, Relationship } from '@/types/api';
import type { ColorPalette } from '@/constants/colors';

const RELATIONSHIP_LABELS: Record<Relationship, string> = {
  self: 'Me',
  parent: 'Parent',
  spouse: 'Spouse',
  child: 'Child',
  sibling: 'Sibling',
  other: 'Other',
};

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

interface Props {
  profile: Profile;
  onPress: () => void;
  style?: ViewStyle;
}

export function ProfileCard({ profile, onPress, style }: Props) {
  const Colors = useColors();
  const Shadow = useShadow();
  const color = getRelationshipColors(Colors)[profile.relationship];

  const handlePress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    onPress();
  };

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => [
        {
          backgroundColor: Colors.surface,
          borderRadius: BorderRadius.lg,
          padding: Spacing.md,
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.md,
          opacity: pressed ? 0.85 : 1,
          ...Shadow.sm,
        },
        style,
      ]}
    >
      {/* Avatar */}
      <View
        style={{
          width: 52,
          height: 52,
          borderRadius: BorderRadius.full,
          backgroundColor: color + '20',
          alignItems: 'center',
          justifyContent: 'center',
          borderWidth: 2,
          borderColor: color,
        }}
      >
        <Text style={{ fontSize: FontSize.lg, fontWeight: FontWeight.bold, color }}>
          {getInitials(profile.name)}
        </Text>
      </View>

      {/* Info */}
      <View style={{ flex: 1 }}>
        <Text
          style={{
            fontSize: FontSize.md,
            fontWeight: FontWeight.semibold,
            color: Colors.text,
          }}
          selectable
        >
          {profile.name}
        </Text>
        <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 }}>
          {profile.date_of_birth
            ? `${new Date().getFullYear() - new Date(profile.date_of_birth).getFullYear()} yrs`
            : '–'}
          {profile.blood_type ? ` · ${profile.blood_type}` : ''}
        </Text>
      </View>

      {/* Relationship badge */}
      <View
        style={{
          backgroundColor: color + '18',
          paddingHorizontal: Spacing.sm,
          paddingVertical: Spacing.xs,
          borderRadius: BorderRadius.full,
          borderWidth: 1,
          borderColor: color + '40',
        }}
      >
        <Text style={{ fontSize: FontSize.xs, fontWeight: FontWeight.semibold, color }}>
          {RELATIONSHIP_LABELS[profile.relationship]}
        </Text>
      </View>
    </Pressable>
  );
}
