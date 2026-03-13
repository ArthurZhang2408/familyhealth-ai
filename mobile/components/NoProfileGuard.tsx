import { View, Text, Pressable, ActivityIndicator } from 'react-native';
import { Icon } from '@/components/Icon';
import { useRouter } from 'expo-router';
import Animated, { FadeIn, FadeInUp } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { useProfileStore } from '@/stores/profile';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

interface Props {
  children: React.ReactNode;
}

export function NoProfileGuard({ children }: Props) {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const hydrated = useProfileStore((s) => s._hydrated);

  // Wait for AsyncStorage to rehydrate before deciding — avoids flash of guard
  if (!hydrated) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.background }}>
        <ActivityIndicator size="small" color={Colors.textMuted} />
      </View>
    );
  }

  if (!activeProfile) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.xl }}>
        <Animated.View entering={FadeIn.duration(300)} style={{ alignItems: 'center' }}>
          <View
            style={{
              width: 48,
              height: 48,
              borderRadius: BorderRadius.lg,
              borderCurve: 'continuous',
              backgroundColor: Colors.primary + '12',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: Spacing.md,
            }}
          >
            <Icon name="people" size={24} color={Colors.primary} />
          </View>
        </Animated.View>
        <Animated.Text
          entering={FadeInUp.delay(100).duration(250)}
          style={{ fontSize: FontSize.xl, fontWeight: FontWeight.bold, color: Colors.text, textAlign: 'center' }}
        >
          Select a profile
        </Animated.Text>
        <Animated.Text
          entering={FadeInUp.delay(200).duration(250)}
          style={{
            fontSize: FontSize.md,
            color: Colors.textSecondary,
            textAlign: 'center',
            marginTop: Spacing.sm,
            marginBottom: Spacing.lg,
          }}
        >
          Choose a family member to get started.
        </Animated.Text>
        <Animated.View entering={FadeInUp.delay(300).duration(250)}>
          <Pressable
            onPress={() => {
              if (process.env.EXPO_OS === 'ios') {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              }
              router.push('/profile-picker');
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
              Choose profile
            </Text>
          </Pressable>
        </Animated.View>
      </View>
    );
  }

  return <>{children}</>;
}
