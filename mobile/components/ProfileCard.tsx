import { View, Text, Pressable, type ViewStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import Svg, { Circle } from 'react-native-svg';
import { useCallback, useRef } from 'react';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { Profile, Relationship } from '@/types/api';
import type { ColorPalette } from '@/constants/colors';

const RELATIONSHIP_LABELS: Record<string, string> = {
  self: 'Me',
  parent: 'Parent', father: 'Father', mother: 'Mother',
  spouse: 'Spouse',
  child: 'Child', son: 'Son', daughter: 'Daughter',
  sibling: 'Sibling', brother: 'Brother', sister: 'Sister',
  grandparent: 'Grandparent', grandfather: 'Grandfather', grandmother: 'Grandmother',
  other: 'Other',
};

const REL_COLOR_MAP: Record<string, keyof ColorPalette> = {
  self: 'relationshipSelf',
  parent: 'relationshipParent', father: 'relationshipParent', mother: 'relationshipParent',
  spouse: 'relationshipSpouse',
  child: 'relationshipChild', son: 'relationshipChild', daughter: 'relationshipChild',
  sibling: 'relationshipSibling', brother: 'relationshipSibling', sister: 'relationshipSibling',
  grandparent: 'relationshipOther', grandfather: 'relationshipOther', grandmother: 'relationshipOther',
  other: 'relationshipOther',
};

function getRelationshipColor(Colors: ColorPalette, rel: string): string {
  return Colors[REL_COLOR_MAP[rel] ?? 'relationshipOther'];
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

export function getProfileCompleteness(profile: Profile): number {
  const arr = (v: unknown) => Array.isArray(v) && v.length > 0;
  const obj = (v: unknown) => v != null && typeof v === 'object' && Object.keys(v).length > 0;
  let score = 0;
  if (profile.date_of_birth) score += 20;
  if (profile.sex) score += 15;
  if (arr(profile.allergies)) score += 15;
  if (arr(profile.medications)) score += 20;
  if (arr(profile.medical_conditions)) score += 15;
  if (profile.height_cm || profile.weight_kg) score += 10;
  if (obj(profile.family_history)) score += 5;
  return score;
}

const AVATAR_SIZE = 52;
const RING_SIZE = 58;
const RING_STROKE = 2.5;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

interface Props {
  profile: Profile;
  onPress: () => void;
  onLongPress?: (x: number, y: number, width: number, height: number) => void;
  style?: ViewStyle;
}

export function ProfileCard({ profile, onPress, onLongPress, style }: Props) {
  const Colors = useColors();
  const Shadow = useShadow();
  const viewRef = useRef<View>(null);
  const color = getRelationshipColor(Colors, profile.relationship);
  const completeness = getProfileCompleteness(profile);

  const handlePress = useCallback(() => {
    if (process.env.EXPO_OS === 'ios')
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    onPress();
  }, [onPress]);

  const handleLongPress = useCallback(() => {
    if (!onLongPress) return;
    if (process.env.EXPO_OS === 'ios')
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    viewRef.current?.measureInWindow((x, y, w, h) => {
      onLongPress(x, y, w, h);
    });
  }, [onLongPress]);

  const strokeDashoffset =
    RING_CIRCUMFERENCE - (completeness / 100) * RING_CIRCUMFERENCE;

  return (
    <View ref={viewRef} collapsable={false}>
      <Pressable
        onPress={handlePress}
        onLongPress={onLongPress ? handleLongPress : undefined}
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
        {/* Avatar with completeness ring */}
        <View
          style={{
            width: RING_SIZE,
            height: RING_SIZE,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {completeness < 100 && (
            <Svg
              width={RING_SIZE}
              height={RING_SIZE}
              style={{
                position: 'absolute',
                transform: [{ rotate: '-90deg' }],
              }}
            >
              {/* Background track */}
              <Circle
                cx={RING_SIZE / 2}
                cy={RING_SIZE / 2}
                r={RING_RADIUS}
                stroke={Colors.border}
                strokeWidth={RING_STROKE}
                fill="none"
                opacity={0.3}
              />
              {/* Progress arc */}
              <Circle
                cx={RING_SIZE / 2}
                cy={RING_SIZE / 2}
                r={RING_RADIUS}
                stroke={Colors.primary}
                strokeWidth={RING_STROKE}
                fill="none"
                strokeDasharray={`${RING_CIRCUMFERENCE}`}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
              />
            </Svg>
          )}
          <View
            style={{
              width: AVATAR_SIZE,
              height: AVATAR_SIZE,
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
              ? `${(() => { const b = new Date(profile.date_of_birth); const t = new Date(); let a = t.getFullYear() - b.getFullYear(); if (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate())) a--; return a; })()} yrs`
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
            {RELATIONSHIP_LABELS[profile.relationship] ?? profile.relationship}
          </Text>
        </View>
      </Pressable>
    </View>
  );
}
