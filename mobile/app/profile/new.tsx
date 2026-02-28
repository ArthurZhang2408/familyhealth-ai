import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  ScrollView,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useCreateProfile } from '@/hooks/useProfiles';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { Relationship } from '@/types/api';

const RELATIONSHIPS: { value: Relationship; label: string }[] = [
  { value: 'self', label: 'Myself' },
  { value: 'parent', label: 'Parent' },
  { value: 'spouse', label: 'Spouse' },
  { value: 'child', label: 'Child' },
  { value: 'sibling', label: 'Sibling' },
  { value: 'other', label: 'Other' },
];

export default function NewProfileScreen() {
  const Colors = useColors();
  const Shadow = useShadow();
  const router = useRouter();
  const createProfile = useCreateProfile();
  const [name, setName] = useState('');
  const [relationship, setRelationship] = useState<Relationship>('self');

  const handleCreate = async () => {
    if (!name.trim()) {
      Alert.alert('Name required', 'Please enter a name for this profile.');
      return;
    }
    try {
      await createProfile.mutateAsync({ name: name.trim(), relationship });
      router.back();
    } catch (err: unknown) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Could not create profile.');
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: Colors.surface }}
      contentContainerStyle={{ padding: Spacing.md, gap: Spacing.lg }}
      keyboardShouldPersistTaps="handled"
    >
      {/* Name */}
      <View style={{ gap: Spacing.xs }}>
        <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.medium, color: Colors.text }}>
          Name
        </Text>
        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="Full name"
          placeholderTextColor={Colors.textMuted}
          autoFocus
          style={{
            backgroundColor: Colors.surfaceSecondary,
            borderWidth: 1,
            borderColor: Colors.border,
            borderRadius: BorderRadius.md,
            borderCurve: 'continuous',
            padding: Spacing.md,
            fontSize: FontSize.md,
            color: Colors.text,
          }}
        />
      </View>

      {/* Relationship */}
      <View style={{ gap: Spacing.sm }}>
        <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.medium, color: Colors.text }}>
          Relationship
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
          {RELATIONSHIPS.map((r) => {
            const selected = relationship === r.value;
            return (
              <Pressable
                key={r.value}
                onPress={() => setRelationship(r.value)}
                style={{
                  paddingHorizontal: Spacing.md,
                  paddingVertical: Spacing.sm,
                  borderRadius: BorderRadius.full,
                  borderCurve: 'continuous',
                  backgroundColor: selected ? Colors.primary : Colors.surface,
                  borderWidth: 1,
                  borderColor: selected ? Colors.primary : Colors.border,
                }}
              >
                <Text
                  style={{
                    fontSize: FontSize.sm,
                    fontWeight: FontWeight.medium,
                    color: selected ? Colors.textInverse : Colors.text,
                  }}
                >
                  {r.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      {/* Submit */}
      <Pressable
        onPress={handleCreate}
        disabled={createProfile.isPending}
        style={({ pressed }) => ({
          backgroundColor: createProfile.isPending ? Colors.primaryLight : Colors.primary,
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          padding: Spacing.md,
          alignItems: 'center',
          opacity: pressed ? 0.9 : 1,
          marginTop: Spacing.sm,
          ...Shadow.sm,
        })}
      >
        <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.textInverse }}>
          {createProfile.isPending ? 'Creating…' : 'Create profile'}
        </Text>
      </Pressable>
    </ScrollView>
  );
}
