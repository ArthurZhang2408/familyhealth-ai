import { useCallback, useRef } from 'react';
import { View, Text, Pressable, ScrollView, useWindowDimensions } from 'react-native';
import { useRouter, Stack, useFocusEffect } from 'expo-router';
import Animated, { useSharedValue, useAnimatedStyle, withTiming, Easing } from 'react-native-reanimated';
import { enterSlideDown, staggerDelay } from '@/constants/animations';
import * as Haptics from 'expo-haptics';
import { Icon, IconName } from '@/components/Icon';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ContextMenuOverlay } from '@/components/ContextMenuOverlay';
import { useProfileStore } from '@/stores/profile';
import { useSessionContextMenu } from '@/hooks/useSessionContextMenu';
import { useColors } from '@/hooks/useColors';
import { useNavSource } from '@/services/navigationSource';
import { relativeTime } from '@/utils/relativeTime';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { SessionType } from '@/hooks/useSession';

// ---------------------------------------------------------------------------
// Config type
// ---------------------------------------------------------------------------

export interface SessionListConfig {
  type: SessionType;
  screenTitle: string;
  emptyIcon: IconName;
  emptyText: string;
  emptyAction: string;
  useData: (pid: string) => { data: { items: any[] } | undefined; isLoading: boolean };
  getTitle: (item: any) => string;
  getId: (item: any) => string;
  getRoute: () => string;
  paramName: string;
  getStatus?: (item: any) => string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SessionListScreen({ config }: { config: SessionListConfig }) {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';
  const { data } = config.useData(pid);
  const itemRefs = useRef<Record<string, View | null>>({});

  const { menu, openMenu, dismissMenu } = useSessionContextMenu(pid);

  // Slide-in-from-left when returning from a session via back button
  const fromList = useNavSource((s) => s.fromList);
  const { width: screenWidth } = useWindowDimensions();
  const slideX = useSharedValue(fromList ? -screenWidth : 0);
  const slideStyle = useAnimatedStyle(() => ({
    flex: 1,
    transform: [{ translateX: slideX.value }],
  }));
  useFocusEffect(
    useCallback(() => {
      if (fromList) {
        slideX.value = -screenWidth;
        slideX.value = withTiming(0, { duration: 300, easing: Easing.out(Easing.cubic) });
      } else {
        slideX.value = 0;
      }
      return () => {
        if (fromList) slideX.value = -screenWidth;
      };
    }, [slideX, screenWidth, fromList]),
  );

  const items = data?.items ?? [];

  if (!data) return <LoadingSpinner />;

  return (
    <>
      <Stack.Screen
        options={{
          title: config.screenTitle,
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
          {items.length === 0 ? (
            <View style={{ alignItems: 'center', paddingVertical: Spacing.xxl, gap: Spacing.md }}>
              <Icon name={config.emptyIcon} size={40} color={Colors.textMuted + '60'} />
              <Text style={{ fontSize: FontSize.md, color: Colors.textMuted }}>
                {config.emptyText}
              </Text>
              <Pressable
                onPress={() => {
                  if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  useNavSource.getState().setPendingMode(config.type);
                  router.navigate('/(main)' as never);
                }}
                style={({ pressed }) => ({
                  paddingHorizontal: Spacing.lg,
                  paddingVertical: Spacing.sm,
                  backgroundColor: Colors.primary + '15',
                  borderRadius: BorderRadius.full,
                  borderCurve: 'continuous',
                  opacity: pressed ? 0.7 : 1,
                })}
              >
                <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.primary }}>
                  {config.emptyAction}
                </Text>
              </Pressable>
            </View>
          ) : (
            items.map((item, i) => {
              const id = config.getId(item);
              const title = config.getTitle(item);
              const status = config.getStatus?.(item);
              return (
                <Animated.View key={id} entering={enterSlideDown(staggerDelay(i))}>
                  <View
                    ref={(ref) => { itemRefs.current[id] = ref; }}
                    collapsable={false}
                  >
                    <Pressable
                      onPress={() => {
                        if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                        useNavSource.getState().setFromList(true);
                        router.navigate({
                          pathname: config.getRoute(),
                          params: { [config.paramName]: id },
                        } as never);
                      }}
                      onLongPress={() => {
                        itemRefs.current[id]?.measureInWindow((x, y, w, h) => {
                          openMenu(config.type, id, title, x, y, w, h);
                        });
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
                          {title}
                        </Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: Spacing.xs, gap: Spacing.sm }}>
                          <Text style={{ fontSize: FontSize.sm, color: Colors.textMuted }}>
                            {relativeTime(item.updated_at || item.created_at)}
                          </Text>
                          {status === 'resolved' && (
                            <View
                              style={{
                                backgroundColor: Colors.success + '18',
                                paddingHorizontal: Spacing.sm,
                                paddingVertical: 2,
                                borderRadius: BorderRadius.full,
                              }}
                            >
                              <Text style={{ fontSize: FontSize.xs, fontWeight: FontWeight.semibold, color: Colors.success }}>
                                Resolved
                              </Text>
                            </View>
                          )}
                        </View>
                      </View>
                      <Icon name="chevron-right" size={18} color={Colors.textMuted} />
                    </Pressable>
                  </View>
                </Animated.View>
              );
            })
          )}
        </ScrollView>
      </Animated.View>

      {menu.visible && (
        <ContextMenuOverlay menu={menu} colors={Colors} onDismiss={dismissMenu} />
      )}
    </>
  );
}
