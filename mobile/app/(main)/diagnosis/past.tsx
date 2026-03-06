import { View, Text, Pressable, ScrollView } from 'react-native';
import { useRouter, Stack } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { useProfileStore } from '@/stores/profile';
import { useDiagnosisSessions } from '@/hooks/useDiagnosis';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

export default function PastDiagnosisScreen() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';
  const { data, isLoading } = useDiagnosisSessions(pid);

  const pastSessions = (data?.items ?? []).filter((s) => s.status !== 'active');

  if (isLoading) return <LoadingSpinner />;

  return (
    <NoProfileGuard>
      <Stack.Screen options={{ title: 'Past Diagnoses' }} />
      <ScrollView
        style={{ flex: 1, backgroundColor: Colors.background }}
        contentContainerStyle={{ padding: Spacing.md, gap: Spacing.sm }}
        contentInsetAdjustmentBehavior="automatic"
      >
        {pastSessions.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: Spacing.xxl }}>
            <Text style={{ fontSize: FontSize.md, color: Colors.textMuted }}>
              No past sessions
            </Text>
          </View>
        ) : (
          pastSessions.map((session, i) => (
            <Animated.View key={session.id} entering={FadeInDown.delay(i * 40).duration(200)}>
              <Pressable
                onPress={() => {
                  if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  router.navigate(`/(main)/diagnosis/${session.id}` as never);
                }}
                style={({ pressed }) => ({
                  backgroundColor: Colors.surface,
                  borderRadius: BorderRadius.lg,
                  borderCurve: 'continuous',
                  padding: Spacing.md,
                  borderWidth: 1,
                  borderColor: Colors.border,
                  opacity: pressed ? 0.85 : 1,
                })}
              >
                <Text
                  style={{ fontSize: FontSize.md, fontWeight: FontWeight.medium, color: Colors.text }}
                  numberOfLines={1}
                >
                  {session.chief_complaint}
                </Text>
                <View style={{ flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.xs }}>
                  <Text style={{ fontSize: FontSize.sm, color: Colors.textMuted }}>
                    {session.status}
                  </Text>
                  <Text style={{ fontSize: FontSize.sm, color: Colors.textMuted }}>
                    {new Date(session.created_at).toLocaleDateString()}
                  </Text>
                </View>
              </Pressable>
            </Animated.View>
          ))
        )}
      </ScrollView>
    </NoProfileGuard>
  );
}
