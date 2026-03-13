import { useCallback } from 'react';
import { View, Text, Pressable, ScrollView, useWindowDimensions } from 'react-native';
import { useRouter, Stack, useFocusEffect } from 'expo-router';
import Animated, { FadeInDown, useSharedValue, useAnimatedStyle, withTiming } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { useProfileStore } from '@/stores/profile';
import { useChatConversations } from '@/hooks/useChat';
import { useColors } from '@/hooks/useColors';
import { relativeTime } from '@/utils/relativeTime';
import { useNavSource } from '@/services/navigationSource';
import { Spacing, FontSize, FontWeight } from '@/constants/theme';

export default function AllChatsScreen() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';
  const { data, isLoading } = useChatConversations(pid);

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
      // If fromList is true, user just came back from a session opened from this list
      if (fromList) {
        slideX.value = -screenWidth;
        slideX.value = withTiming(0, { duration: 250 });
      }
    }, [slideX, screenWidth, fromList]),
  );

  const conversations = data?.items ?? [];

  if (!data) return <LoadingSpinner />;

  return (
    <NoProfileGuard>
      <Stack.Screen
        options={{
          title: 'Chats',
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
          {conversations.length === 0 ? (
            <View style={{ alignItems: 'center', paddingVertical: Spacing.xxl }}>
              <Text style={{ fontSize: FontSize.md, color: Colors.textMuted }}>
                No conversations yet
              </Text>
            </View>
          ) : (
            conversations.map((c, i) => (
              <Animated.View key={c.id} entering={FadeInDown.delay(i * 25).duration(200)}>
                <Pressable
                  onPress={() => {
                    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    useNavSource.getState().setFromList(true);
                    router.navigate({ pathname: '/(main)/chat/[cid]', params: { cid: c.id } } as never);
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
                      {c.topic || 'New conversation'}
                    </Text>
                    <Text
                      style={{
                        fontSize: FontSize.sm,
                        color: Colors.textMuted,
                        marginTop: Spacing.xs,
                      }}
                    >
                      {relativeTime(c.updated_at || c.created_at)}
                    </Text>
                  </View>
                  <Icon name="chevron-right" size={18} color={Colors.textMuted} />
                </Pressable>
              </Animated.View>
            ))
          )}
        </ScrollView>
      </Animated.View>
    </NoProfileGuard>
  );
}
