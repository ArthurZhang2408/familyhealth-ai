import { useState } from 'react';
import { View, Text, Pressable, Modal, StyleSheet, useWindowDimensions } from 'react-native';
import { BlurView } from 'expo-blur';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated from 'react-native-reanimated';
import { enterSlideUp, enterFade } from '@/constants/animations';
import { Icon, IconName } from '@/components/Icon';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { ColorPalette } from '@/constants/colors';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MenuAction = {
  label: string;
  icon: IconName;
  destructive?: boolean;
  onPress: () => void;
};

export interface ContextMenuState {
  visible: boolean;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  actions: MenuAction[];
}

export const MENU_INITIAL: ContextMenuState = {
  visible: false, title: '', x: 0, y: 0, width: 0, height: 0, actions: [],
};

// ---------------------------------------------------------------------------
// Constants (reverse-engineered from iOS 17/18)
// ---------------------------------------------------------------------------

const MENU_ROW_HEIGHT = 44;
const MENU_RADIUS = 13;
const MENU_WIDTH = 250;
const MENU_GAP = 8;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ContextMenuOverlay({
  menu,
  colors: Colors,
  titleFontSize,
  onDismiss,
}: {
  menu: ContextMenuState;
  colors: ColorPalette;
  titleFontSize?: number;
  onDismiss: () => void;
}) {
  const { width: screenWidth, height: screenHeight } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [measuredHeight, setMeasuredHeight] = useState<number | null>(null);

  const highlightWidth = screenWidth - 2 * Spacing.md;
  const highlightLeft = Spacing.md;
  const fontSize = titleFontSize ?? FontSize.md;

  // Use measured height when available, otherwise estimate from original item
  const cardHeight = measuredHeight ?? menu.height;

  // Clamp highlight card so it doesn't extend below the screen
  const maxTop = screenHeight - cardHeight - insets.bottom - MENU_GAP;
  const highlightTop = Math.min(menu.y, maxTop);

  // Menu card positioning (auto-flip above/below)
  const menuCardHeight = menu.actions.length * MENU_ROW_HEIGHT
    + StyleSheet.hairlineWidth * (menu.actions.length - 1);
  const belowY = highlightTop + cardHeight + MENU_GAP;
  const aboveY = highlightTop - MENU_GAP - menuCardHeight;
  const menuTop = belowY + menuCardHeight > screenHeight - insets.bottom ? aboveY : belowY;

  // Menu card left: clamp so it doesn't overflow right edge
  const menuLeft = Math.min(highlightLeft, screenWidth - MENU_WIDTH - Spacing.md);

  return (
    <Modal transparent statusBarTranslucent animationType="none">
      <View style={StyleSheet.absoluteFill} accessibilityViewIsModal>
        {/* Dim scrim */}
        <Animated.View entering={enterFade()} style={StyleSheet.absoluteFill}>
          <Pressable
            onPress={onDismiss}
            accessibilityLabel="Dismiss menu"
            accessibilityRole="button"
            style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' }}
          />
        </Animated.View>

        {/* Highlighted item — floating card at full screen width */}
        <Animated.View
          onLayout={(e) => {
            if (measuredHeight == null) setMeasuredHeight(e.nativeEvent.layout.height);
          }}
          style={{
            position: 'absolute',
            top: highlightTop,
            left: highlightLeft,
            width: highlightWidth,
            minHeight: menu.height,
            borderRadius: BorderRadius.md,
            borderCurve: 'continuous',
            overflow: 'hidden',
            opacity: measuredHeight != null ? 1 : 0,
          }}
        >
          <BlurView
            intensity={60}
            tint="systemChromeMaterialDark"
            style={{
              flex: 1,
              justifyContent: 'center',
              paddingHorizontal: Spacing.sm,
              paddingVertical: Spacing.xs,
            }}
          >
            <Text
              style={{ fontSize, color: Colors.text, fontWeight: FontWeight.semibold }}
              numberOfLines={3}
            >
              {menu.title}
            </Text>
          </BlurView>
        </Animated.View>

        {/* Menu card — iOS-style rounded blur card */}
        {measuredHeight != null && (
          <Animated.View
            entering={enterSlideUp()}
            style={{
              position: 'absolute',
              top: menuTop,
              left: menuLeft,
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
                    accessibilityRole="menuitem"
                    accessibilityLabel={action.label}
                    style={({ pressed }) => ({
                      flexDirection: 'row',
                      alignItems: 'center',
                      height: MENU_ROW_HEIGHT,
                      paddingHorizontal: Spacing.md,
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
        )}
      </View>
    </Modal>
  );
}
