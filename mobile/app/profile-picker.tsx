import { View, Text, Pressable, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { ProfileCard } from '@/components/ProfileCard';
import { EmptyState } from '@/components/EmptyState';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useProfiles } from '@/hooks/useProfiles';
import { useProfileStore } from '@/stores/profile';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

/**
 * Fallback profile picker screen (formSheet).
 * Primary profile selection now happens via the dropdown in ProfilePill.
 * This screen is kept for NoProfileGuard navigation.
 */
export default function ProfilePickerScreen() {
  const Colors = useColors();
  const router = useRouter();
  const { data, isLoading } = useProfiles();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const setActiveProfile = useProfileStore((s) => s.setActiveProfile);

  const profiles = data?.items ?? [];

  const handleSelect = (profile: (typeof profiles)[0]) => {
    if (process.env.EXPO_OS === 'ios') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }
    setActiveProfile(profile);
    router.back();
    setTimeout(() => router.navigate('/(main)'), 150);
  };

  if (isLoading) return <LoadingSpinner />;

  if (profiles.length === 0) {
    return (
      <View style={{ flex: 1, backgroundColor: Colors.surface }}>
        <EmptyState
          title="No profiles yet"
          subtitle="Add a family member to get started."
          action={
            <Pressable
              onPress={() => {
                if (process.env.EXPO_OS === 'ios') {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                }
                router.push('/profile/new');
              }}
              style={({ pressed }) => ({
                backgroundColor: Colors.primary,
                borderRadius: BorderRadius.md,
                borderCurve: 'continuous',
                paddingHorizontal: Spacing.lg,
                paddingVertical: Spacing.sm,
                opacity: pressed ? 0.85 : 1,
              })}
            >
              <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.textInverse }}>
                + Add profile
              </Text>
            </Pressable>
          }
        />
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: Colors.surface }}
      contentContainerStyle={{ padding: Spacing.md, gap: Spacing.sm }}
    >
      {profiles.map((profile) => (
        <ProfileCard
          key={profile.id}
          profile={profile}
          onPress={() => handleSelect(profile)}
          style={
            activeProfile?.id === profile.id
              ? { borderWidth: 2, borderColor: Colors.primary }
              : undefined
          }
        />
      ))}
      <Pressable
        onPress={() => {
          if (process.env.EXPO_OS === 'ios') {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
          }
          router.push('/profile/new');
        }}
        style={({ pressed }) => ({
          backgroundColor: Colors.surfaceSecondary,
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          padding: Spacing.md,
          alignItems: 'center',
          marginTop: Spacing.xs,
          borderWidth: 1,
          borderColor: Colors.border,
          borderStyle: 'dashed',
          opacity: pressed ? 0.85 : 1,
        })}
      >
        <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.primary }}>
          + Add profile
        </Text>
      </Pressable>
    </ScrollView>
  );
}
