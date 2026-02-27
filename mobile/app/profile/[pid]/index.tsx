import { View, Text, Pressable } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { ScreenContainer } from '@/components/ScreenContainer';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useProfile } from '@/hooks/useProfiles';
import { Colors } from '@/constants/colors';
import { Spacing, FontSize, FontWeight, BorderRadius, Shadow } from '@/constants/theme';

interface ActionCardProps {
  title: string;
  subtitle: string;
  color: string;
  onPress: () => void;
}

function ActionCard({ title, subtitle, color, onPress }: ActionCardProps) {
  return (
    <Pressable
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress();
      }}
      style={({ pressed }) => ({
        backgroundColor: Colors.surface,
        borderRadius: BorderRadius.lg,
        padding: Spacing.lg,
        borderLeftWidth: 4,
        borderLeftColor: color,
        opacity: pressed ? 0.85 : 1,
        ...Shadow.sm,
      })}
    >
      <Text style={{ fontSize: FontSize.lg, fontWeight: FontWeight.semibold, color: Colors.text }}>
        {title}
      </Text>
      <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.xs }}>
        {subtitle}
      </Text>
    </Pressable>
  );
}

export default function ProfileDetailScreen() {
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const router = useRouter();
  const { data: profile, isLoading } = useProfile(pid);

  if (isLoading) return <LoadingSpinner />;
  if (!profile) return null;

  return (
    <>
      <Stack.Screen options={{ title: profile.name }} />
      <ScreenContainer>
        {/* Summary card */}
        <View
          style={{
            backgroundColor: Colors.surface,
            borderRadius: BorderRadius.lg,
            padding: Spacing.lg,
            gap: Spacing.sm,
            ...Shadow.sm,
          }}
        >
          <Text style={{ fontSize: FontSize.xl, fontWeight: FontWeight.bold, color: Colors.text }}>
            {profile.name}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
            {profile.date_of_birth && (
              <Chip label={`Age ${new Date().getFullYear() - new Date(profile.date_of_birth).getFullYear()}`} />
            )}
            {profile.sex && <Chip label={profile.sex} />}
            {profile.blood_type && <Chip label={profile.blood_type} color={Colors.error} />}
          </View>
          {profile.allergies.length > 0 && (
            <View style={{ backgroundColor: Colors.errorLight, borderRadius: BorderRadius.sm, padding: Spacing.sm }}>
              <Text style={{ fontSize: FontSize.xs, fontWeight: FontWeight.semibold, color: Colors.error }}>
                ALLERGIES
              </Text>
              <Text style={{ fontSize: FontSize.sm, color: Colors.text }}>
                {profile.allergies.map((a) => a.name).join(', ')}
              </Text>
            </View>
          )}
        </View>

        {/* Actions */}
        <Text
          style={{
            fontSize: FontSize.xs,
            fontWeight: FontWeight.semibold,
            color: Colors.textMuted,
            textTransform: 'uppercase',
            letterSpacing: 0.8,
          }}
        >
          AI Features
        </Text>

        <ActionCard
          title="Diagnosis"
          subtitle="Describe symptoms and get an AI-assisted assessment"
          color={Colors.primary}
          onPress={() => router.push(`/profile/${pid}/diagnosis`)}
        />
        <ActionCard
          title="Report Analysis"
          subtitle="Upload lab reports for AI interpretation"
          color={Colors.accent}
          onPress={() => router.push(`/profile/${pid}/reports`)}
        />
        <ActionCard
          title="Health Chat"
          subtitle="Ask health questions about this profile"
          color={Colors.info}
          onPress={() => router.push(`/profile/${pid}/chat`)}
        />
      </ScreenContainer>
    </>
  );
}

function Chip({ label, color = Colors.primary }: { label: string; color?: string }) {
  return (
    <View
      style={{
        backgroundColor: color + '18',
        paddingHorizontal: Spacing.sm,
        paddingVertical: 2,
        borderRadius: BorderRadius.full,
        borderWidth: 1,
        borderColor: color + '40',
      }}
    >
      <Text style={{ fontSize: FontSize.xs, fontWeight: FontWeight.medium, color }}>
        {label}
      </Text>
    </View>
  );
}
