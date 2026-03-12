import { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  Pressable,
  ScrollView,
  Modal,
  StyleSheet,
  Alert,
  useWindowDimensions,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { useRouter } from 'expo-router';
import Animated, {
  FadeIn,
  FadeInUp,
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withDelay,
  runOnJS,
  Easing,
} from 'react-native-reanimated';
import { BlurView } from 'expo-blur';
import { Icon, type IconName } from '@/components/Icon';
import { ProfileCard } from '@/components/ProfileCard';
import { useProfileStore } from '@/stores/profile';
import { useProfiles, useDeleteProfile } from '@/hooks/useProfiles';
import { useColors } from '@/hooks/useColors';
import { useHeaderScale } from '@/hooks/useHeaderScale';
import { FontWeight, Spacing, FontSize, BorderRadius } from '@/constants/theme';
import { useShadow } from '@/hooks/useShadow';
import type { Profile } from '@/types/api';
import type { ColorPalette } from '@/constants/colors';

// ── Context menu types ───────────────────────────────────────────────────────

type MenuAction = { label: string; icon: IconName; destructive?: boolean; onPress: () => void };

interface ContextMenuState {
  visible: boolean;
  profile: Profile | null;
  x: number; y: number; width: number; height: number;
  actions: MenuAction[];
}

const MENU_INITIAL: ContextMenuState = {
  visible: false, profile: null, x: 0, y: 0, width: 0, height: 0, actions: [],
};

const MENU_ROW_HEIGHT = 44;
const MENU_RADIUS = 13;
const MENU_WIDTH = 250;
const MENU_GAP = 8;
const HIGHLIGHT_RADIUS = 12;

const ANIM_DURATION = 280;
const EASING = Easing.bezier(0.2, 0.9, 0.3, 1);

// ── ProfilePill ──────────────────────────────────────────────────────────────

export function ProfilePill() {
  const Colors = useColors();
  const Shadow = useShadow();
  const router = useRouter();
  const header = useHeaderScale();
  const { width: screenWidth, height: screenHeight } = useWindowDimensions();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const setActiveProfile = useProfileStore((s) => s.setActiveProfile);
  const { data } = useProfiles();
  const deleteProfile = useDeleteProfile();

  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState<ContextMenuState>(MENU_INITIAL);
  const dismissMenu = useCallback(() => setMenu(MENU_INITIAL), []);

  const pillRef = useRef<View>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);
  // Pill's measured position (screen-absolute)
  const [pillRect, setPillRect] = useState({ x: 0, y: 0, w: 0, h: 0 });

  const profiles = data?.items ?? [];
  const label = activeProfile?.name ?? 'Select profile';
  const textColor = activeProfile ? Colors.text : Colors.textSecondary;

  // Shared values for scale-from-pill animation
  const progress = useSharedValue(0);

  // Dropdown target geometry
  const dropdownLeft = Spacing.md;
  const dropdownRight = Spacing.md;
  const dropdownTop = pillRect.y + pillRect.h + Spacing.sm;
  const dropdownWidth = screenWidth - dropdownLeft - dropdownRight;
  const maxDropdownHeight = Math.min(screenHeight * 0.6, screenHeight - dropdownTop - 20);

  // Pill center relative to dropdown target
  const pillCenterX = pillRect.x + pillRect.w / 2;
  const pillCenterY = pillRect.y + pillRect.h / 2;
  const dropdownCenterX = dropdownLeft + dropdownWidth / 2;
  const dropdownCenterY = dropdownTop + maxDropdownHeight / 2;

  // Transform origin offset
  const originX = pillCenterX - dropdownCenterX;
  const originY = pillCenterY - dropdownCenterY;

  const scaleFrom = Math.min(pillRect.w / Math.max(dropdownWidth, 1), 0.3);

  const dropdownAnimStyle = useAnimatedStyle(() => {
    const p = progress.value;
    const scale = scaleFrom + (1 - scaleFrom) * p;
    const translateX = originX * (1 - p);
    const translateY = originY * (1 - p);
    return {
      opacity: p,
      transform: [
        { translateX },
        { translateY },
        { scale },
      ],
    };
  });

  const backdropAnimStyle = useAnimatedStyle(() => ({
    opacity: progress.value,
  }));

  const handlePillPress = useCallback(() => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    pillRef.current?.measureInWindow((x, y, w, h) => {
      setPillRect({ x, y, w, h });
      setOpen(true);
      progress.value = 0;
      progress.value = withTiming(1, { duration: ANIM_DURATION, easing: EASING });
    });
  }, [progress]);

  const handleDismiss = useCallback(() => {
    progress.value = withTiming(0, { duration: 180, easing: Easing.in(Easing.ease) }, () => {
      runOnJS(setOpen)(false);
      runOnJS(setMenu)(MENU_INITIAL);
    });
  }, [progress]);

  const handleSelect = useCallback((profile: Profile) => {
    if (process.env.EXPO_OS === 'ios') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    const changed = profile.id !== activeProfile?.id;
    setActiveProfile(profile);
    // Quick close animation
    progress.value = withTiming(0, { duration: 150 }, () => {
      runOnJS(setOpen)(false);
      // Navigate to home when switching profiles so we don't stay on a
      // stale conversation that belongs to the previous profile.
      if (changed) runOnJS(router.navigate)('/(main)' as never);
    });
  }, [setActiveProfile, progress, activeProfile, router]);

  const handleNavigate = useCallback((path: string) => {
    // Animate closed, then navigate
    progress.value = withTiming(0, { duration: 150 }, () => {
      runOnJS(setOpen)(false);
      runOnJS(router.push)(path as never);
    });
  }, [progress, router]);

  const openProfileMenu = useCallback((profile: Profile, x: number, y: number, w: number, h: number) => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const actions: MenuAction[] = [
      {
        label: 'Edit',
        icon: 'pencil',
        onPress: () => {
          setMenu(MENU_INITIAL);
          handleNavigate(`/profile/new?pid=${profile.id}`);
        },
      },
      {
        label: 'Delete',
        icon: 'trash',
        destructive: true,
        onPress: () => {
          setMenu(MENU_INITIAL);
          progress.value = withTiming(0, { duration: 150 }, () => {
            runOnJS(setOpen)(false);
          });
          timerRef.current = setTimeout(() => {
            Alert.alert(
              'Delete profile',
              `Are you sure you want to delete "${profile.name}"? This will remove all sessions and memories.`,
              [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Delete',
                  style: 'destructive',
                  onPress: () => {
                    deleteProfile.mutate(profile.id);
                    if (activeProfile?.id === profile.id) setActiveProfile(null);
                  },
                },
              ],
            );
          }, 200);
        },
      },
    ];
    setMenu({ visible: true, profile, x, y, width: w, height: h, actions });
  }, [handleNavigate, deleteProfile, activeProfile, setActiveProfile, progress]);

  return (
    <>
      <View ref={pillRef} collapsable={false}>
        <Pressable
          onPress={handlePillPress}
          style={({ pressed }) => ({
            flexDirection: 'row',
            alignItems: 'center',
            gap: Spacing.xs,
            height: header.buttonSize,
            paddingHorizontal: Spacing.sm,
            borderRadius: BorderRadius.full,
            borderCurve: 'continuous',
            opacity: pressed ? 0.6 : 1,
          })}
        >
          <Text
            style={{
              fontSize: header.titleSize,
              fontWeight: activeProfile ? FontWeight.semibold : FontWeight.medium,
              color: textColor,
            }}
            numberOfLines={1}
          >
            {label}
          </Text>
          <Icon name={open ? 'chevron-up' : 'chevron-down'} size={header.accessorySize} color={Colors.textMuted} />
        </Pressable>
      </View>

      {open && (
        <Modal transparent statusBarTranslucent animationType="none">
          <View style={StyleSheet.absoluteFill}>
            {/* Backdrop */}
            <Animated.View style={[StyleSheet.absoluteFill, backdropAnimStyle]}>
              <Pressable
                onPress={handleDismiss}
                style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.3)' }}
              />
            </Animated.View>

            {/* Dropdown card — scales from pill position */}
            <Animated.View
              style={[
                {
                  position: 'absolute',
                  top: dropdownTop,
                  left: dropdownLeft,
                  right: dropdownRight,
                  maxHeight: maxDropdownHeight,
                },
                dropdownAnimStyle,
              ]}
            >
              <View
                style={{
                  flex: 1,
                  borderRadius: BorderRadius.lg,
                  borderCurve: 'continuous',
                  backgroundColor: Colors.surface,
                  ...Shadow.lg,
                  overflow: 'hidden',
                }}
              >
              <ScrollView
                contentContainerStyle={{ padding: Spacing.sm, gap: Spacing.sm }}
                keyboardShouldPersistTaps="handled"
                bounces={false}
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
                    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    handleNavigate('/profile/new');
                  }}
                  style={({ pressed }) => ({
                    backgroundColor: Colors.surfaceSecondary,
                    borderRadius: BorderRadius.md,
                    borderCurve: 'continuous',
                    padding: Spacing.md,
                    alignItems: 'center',
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
              </View>
            </Animated.View>

            {/* Context menu overlay (for long-press edit/delete) */}
            {menu.visible && (
              <ContextMenuOverlay menu={menu} colors={Colors} onDismiss={dismissMenu} />
            )}
          </View>
        </Modal>
      )}
    </>
  );
}

// ── Context Menu Overlay ─────────────────────────────────────────────────────

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
    <>
      {/* Darker scrim to make the highlighted card pop */}
      <Animated.View entering={FadeIn.duration(150)} style={StyleSheet.absoluteFill}>
        <Pressable onPress={onDismiss} style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)' }} />
      </Animated.View>

      {/* Highlighted clone — render actual ProfileCard at measured position, elevated */}
      {menu.profile && (
        <Animated.View
          entering={FadeIn.duration(200)}
          style={{
            position: 'absolute',
            top: menu.y,
            left: menu.x,
            width: menu.width,
            // Bright glow behind the card
            shadowColor: Colors.primary,
            shadowOffset: { width: 0, height: 0 },
            shadowOpacity: 0.3,
            shadowRadius: 12,
            elevation: 10,
          }}
        >
          <ProfileCard
            profile={menu.profile}
            onPress={onDismiss}
          />
        </Animated.View>
      )}

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
                <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: 'rgba(255,255,255,0.12)' }} />
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
    </>
  );
}
