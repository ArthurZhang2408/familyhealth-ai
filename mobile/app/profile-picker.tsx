import { useState, useCallback, useRef } from 'react';
import { View, Text, Pressable, ScrollView, Alert, StyleSheet, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import Animated, { FadeIn, FadeInUp } from 'react-native-reanimated';
import { BlurView } from 'expo-blur';
import * as Haptics from 'expo-haptics';
import { ProfileCard } from '@/components/ProfileCard';
import { EmptyState } from '@/components/EmptyState';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Icon, IconName } from '@/components/Icon';
import { useProfiles, useDeleteProfile } from '@/hooks/useProfiles';
import { useProfileStore } from '@/stores/profile';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { Profile } from '@/types/api';
import type { ColorPalette } from '@/constants/colors';

// ---------------------------------------------------------------------------
// Context menu types
// ---------------------------------------------------------------------------

type MenuAction = { label: string; icon: IconName; destructive?: boolean; onPress: () => void };

interface ContextMenuState {
  visible: boolean;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  actions: MenuAction[];
}

const MENU_INITIAL: ContextMenuState = {
  visible: false, title: '', x: 0, y: 0, width: 0, height: 0, actions: [],
};

// ---------------------------------------------------------------------------
// Context menu overlay (iOS context menu style)
// ---------------------------------------------------------------------------

const MENU_ROW_HEIGHT = 44;
const MENU_RADIUS = 13;
const MENU_WIDTH = 250;
const MENU_GAP = 8;
const HIGHLIGHT_RADIUS = 12;

function ContextMenuOverlay({
  menu,
  colors: Colors,
  onDismiss,
}: {
  menu: ContextMenuState;
  colors: ColorPalette;
  onDismiss: () => void;
}) {
  const { height: screenHeight } = useWindowDimensions();
  const menuCardHeight = menu.actions.length * MENU_ROW_HEIGHT + StyleSheet.hairlineWidth * (menu.actions.length - 1);
  const belowY = menu.y + menu.height + MENU_GAP;
  const aboveY = menu.y - MENU_GAP - menuCardHeight;
  const menuTop = belowY + menuCardHeight > screenHeight - 20 ? aboveY : belowY;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      {/* Dim scrim */}
      <Animated.View entering={FadeIn.duration(200)} style={StyleSheet.absoluteFill}>
        <Pressable onPress={onDismiss} style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' }} />
      </Animated.View>

        {/* Highlighted item — floating card at measured position */}
        <Animated.View
          entering={FadeIn.duration(200)}
          style={{
            position: 'absolute',
            top: menu.y,
            left: menu.x,
            width: menu.width,
            height: menu.height,
            borderRadius: HIGHLIGHT_RADIUS,
            borderCurve: 'continuous',
            overflow: 'hidden',
          }}
        >
          <BlurView
            intensity={60}
            tint="systemChromeMaterialDark"
            style={{
              flex: 1,
              justifyContent: 'center',
              paddingHorizontal: Spacing.sm,
            }}
          >
            <Text
              style={{ fontSize: FontSize.md, color: Colors.text, fontWeight: FontWeight.semibold }}
              numberOfLines={1}
            >
              {menu.title}
            </Text>
          </BlurView>
        </Animated.View>

        {/* Menu card */}
        <Animated.View
          entering={FadeInUp.duration(250).damping(20).stiffness(200)}
          style={{
            position: 'absolute',
            top: menuTop,
            left: menu.x,
            width: MENU_WIDTH,
            borderRadius: MENU_RADIUS,
            borderCurve: 'continuous',
            overflow: 'hidden',
          }}
        >
          <BlurView intensity={80} tint="systemThickMaterialDark">
            {menu.actions.map((action, i) => (
              <View key={action.label}>
                {i > 0 && (
                  <View style={{
                    height: StyleSheet.hairlineWidth,
                    backgroundColor: 'rgba(255,255,255,0.12)',
                  }} />
                )}
                <Pressable
                  onPress={action.onPress}
                  style={({ pressed }) => ({
                    flexDirection: 'row',
                    alignItems: 'center',
                    height: MENU_ROW_HEIGHT,
                    paddingHorizontal: 16,
                    backgroundColor: pressed ? 'rgba(255,255,255,0.08)' : 'transparent',
                  })}
                >
                  <Icon
                    name={action.icon}
                    size={18}
                    color={action.destructive ? Colors.error : Colors.text}
                  />
                  <Text
                    style={{
                      flex: 1,
                      fontSize: 17,
                      marginLeft: 12,
                      color: action.destructive ? Colors.error : Colors.text,
                    }}
                  >
                    {action.label}
                  </Text>
                </Pressable>
              </View>
            ))}
          </BlurView>
        </Animated.View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ProfilePickerScreen() {
  const Colors = useColors();
  const router = useRouter();
  const { data, isLoading } = useProfiles();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const setActiveProfile = useProfileStore((s) => s.setActiveProfile);
  const deleteProfile = useDeleteProfile();
  const containerRef = useRef<View>(null);
  const containerOffsetRef = useRef({ x: 0, y: 0 });

  const [menu, setMenu] = useState<ContextMenuState>(MENU_INITIAL);
  const dismissMenu = useCallback(() => setMenu(MENU_INITIAL), []);

  const profiles = data?.items ?? [];

  const handleSelect = (profile: (typeof profiles)[0]) => {
    if (process.env.EXPO_OS === 'ios') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }
    setActiveProfile(profile);
    router.back();
    // Navigate to fresh new-conversation screen after dismissing picker
    setTimeout(() => router.navigate('/(main)'), 150);
  };

  const openProfileMenu = useCallback((profile: Profile, x: number, y: number, w: number, h: number) => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    // measureInWindow gives screen-absolute coords; subtract container offset
    // so the overlay (rendered inside this container) positions correctly.
    const ox = containerOffsetRef.current.x;
    const oy = containerOffsetRef.current.y;
    x -= ox;
    y -= oy;
    const actions: MenuAction[] = [
      {
        label: 'Edit',
        icon: 'pencil' as IconName,
        onPress: () => {
          dismissMenu();
          router.push(`/profile/new?pid=${profile.id}` as never);
        },
      },
      {
        label: 'Delete',
        icon: 'trash' as IconName,
        destructive: true,
        onPress: () => {
          dismissMenu();
          setTimeout(() => {
            Alert.alert(
              'Delete profile',
              `Are you sure you want to delete "${profile.name}"? This will also delete all their sessions and memories.`,
              [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Delete',
                  style: 'destructive',
                  onPress: () => {
                    deleteProfile.mutate(profile.id);
                    if (activeProfile?.id === profile.id) {
                      setActiveProfile(null);
                    }
                  },
                },
              ],
            );
          }, 150);
        },
      },
    ];
    setMenu({ visible: true, title: profile.name, x, y, width: w, height: h, actions });
  }, [dismissMenu, router, deleteProfile, activeProfile, setActiveProfile]);

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
    <View
      ref={containerRef}
      collapsable={false}
      style={{ flex: 1, backgroundColor: Colors.surface }}
      onLayout={() => {
        containerRef.current?.measureInWindow((x, y) => {
          containerOffsetRef.current = { x, y };
        });
      }}
    >
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: Spacing.md, gap: Spacing.sm }}
        scrollEnabled={!menu.visible}
      >
        {profiles.map((profile) => (
          <ProfileCard
            key={profile.id}
            profile={profile}
            onPress={() => handleSelect(profile)}
            onLongPress={(x, y, w, h) => openProfileMenu(profile, x, y, w, h)}
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

      {/* Context menu overlay */}
      {menu.visible && (
        <ContextMenuOverlay
          menu={menu}
          colors={Colors}
          onDismiss={dismissMenu}
        />
      )}
    </View>
  );
}
