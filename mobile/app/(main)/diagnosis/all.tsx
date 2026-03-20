import { useCallback } from 'react';
import { View, Text, Pressable, ScrollView, useWindowDimensions } from 'react-native';
import { useRouter, Stack, useFocusEffect } from 'expo-router';
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { enterSlideDown, staggerDelay, Springs } from '@/constants/animations';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useProfileStore } from '@/stores/profile';
import { useDiagnosisSessions } from '@/hooks/useDiagnosis';
import { useColors } from '@/hooks/useColors';
import { relativeTime } from '@/utils/relativeTime';
import { useNavSource } from '@/services/navigationSource';
import { Spacing, FontSize, FontWeight } from '@/constants/theme';

export default function AllSessionsScreen() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';
  const { data, isLoading } = useDiagnosisSessions(pid);

  // Slide-in-from-left when returning from a session via back button
  const fromList = useNavSource((s) => s.fromList);
  const { width: screenWidth } = useWindowDimensions();
  const slideX = useSharedValue(0);
  const slideStyle = useAnimatedStyle(() => ({
    flex: 1,
    transform: [{ translateX: slideX.value }],
  }));
  useFocusEffect(
    useCallback(() => {
      if (fromList) {
        slideX.value = -screenWidth;
        slideX.value = withSpring(0, Springs.gentle);
      }
    }, [slideX, screenWidth, fromList]),
  );

  const sessions = data?.items ?? [];

  if (!data) return <LoadingSpinner />;

  return (
    <>
      <Stack.Screen
        options={{
          title: 'Sessions',
          headerRight: () => (
            <HeaderIconButton icon="pen-square" onPress={() => router.navigate('/(main)' as never)} />
          ),
        }}
      />
      <Animated.View style={slideStyle}>
        <ScrollView
          style={{ flex: 1, backgroundColor: Colors.background }}
          contentContainerStyle={{ paddingVertical: Spacing.sm }}
          showsVerticalScrollIndicator={false}
        >
          {sessions.length === 0 ? (
            <View style={{ alignItems: 'center', paddingVertical: Spacing.xxl }}>
              <Text style={{ fontSize: FontSize.md, color: Colors.textMuted }}>
                No sessions yet
              </Text>
            </View>
          ) : (
            sessions.map((s, i) => (
              <Animated.View key={s.id} entering={enterSlideDown(staggerDelay(i))}>
                <Pressable
                  onPress={() => {
                    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    useNavSource.getState().setFromList(true);
                    router.navigate({ pathname: '/(main)/diagnosis/[sid]', params: { sid: s.id } } as never);
                  }}
                  style={({ pressed }) => ({
                    flexDirection: 'row',
                    alignItems: 'center',
                    paddingHorizontal: Spacing.md,
                    paddingVertical: Spacing.md,
                    backgroundColor: pressed ? Colors.surfaceSecondary : 'transparent',
                  })}
                >
                  <View style={{ flex: 1, marginRight: Spacing.sm }}>
                    <Text
                      style={{
                        fontSize: FontSize.md,
                        fontWeight: FontWeight.medium,
                        color: Colors.text,
                      }}
                      numberOfLines={1}
                    >
                      {s.title || s.chief_complaint}
                    </Text>
                    <Text
                      style={{
                        fontSize: FontSize.sm,
                        color: Colors.textMuted,
                        marginTop: Spacing.xs,
                      }}
                    >
                      {relativeTime(s.updated_at || s.created_at)}
                    </Text>
                  </View>
                  <Icon name="chevron-right" size={18} color={Colors.textMuted} />
                </Pressable>
              </Animated.View>
            ))
          )}
        </ScrollView>
      </Animated.View>
    </>
  );
}
