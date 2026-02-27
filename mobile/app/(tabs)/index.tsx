import { View, Text, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { Stack } from 'expo-router';
import { ScreenContainer } from '@/components/ScreenContainer';
import { ProfileCard } from '@/components/ProfileCard';
import { EmptyState } from '@/components/EmptyState';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useProfiles } from '@/hooks/useProfiles';
import { Colors } from '@/constants/colors';
import { Spacing, FontSize, FontWeight, BorderRadius, Shadow } from '@/constants/theme';

export default function HomeScreen() {
  const router = useRouter();
  const { data, isLoading } = useProfiles();

  if (isLoading) return <LoadingSpinner />;

  const profiles = data?.items ?? [];

  return (
    <>
      <Stack.Screen options={{ title: 'Profiles', headerShown: true }} />
      <ScreenContainer>
        {profiles.length === 0 ? (
          <EmptyState
            title="No profiles yet"
            subtitle="Add a family member to get started tracking their health."
            action={
              <AddProfileButton onPress={() => router.push('/profile/new')} />
            }
          />
        ) : (
          <>
            {profiles.map((profile) => (
              <ProfileCard
                key={profile.id}
                profile={profile}
                onPress={() => router.push(`/profile/${profile.id}`)}
              />
            ))}
            <AddProfileButton onPress={() => router.push('/profile/new')} />
          </>
        )}
      </ScreenContainer>
    </>
  );
}

function AddProfileButton({ onPress }: { onPress: () => void }) {
  return (
    <Pressable
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress();
      }}
      style={({ pressed }) => ({
        backgroundColor: Colors.primary,
        borderRadius: BorderRadius.md,
        padding: Spacing.md,
        alignItems: 'center',
        opacity: pressed ? 0.85 : 1,
        ...Shadow.sm,
      })}
    >
      <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.textInverse }}>
        + Add profile
      </Text>
    </Pressable>
  );
}
