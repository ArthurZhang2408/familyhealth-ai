import { useCallback, useRef, useState } from 'react';
import { View, Text, Pressable, ScrollView, ActivityIndicator, Alert, Modal, StyleSheet, useWindowDimensions } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { BlurView } from 'expo-blur';
import { Icon, IconName } from '@/components/Icon';
import { useRouter, usePathname } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { DrawerContentComponentProps } from '@react-navigation/drawer';
import Animated, { FadeIn, FadeInDown, FadeInUp } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { useProfileStore } from '@/stores/profile';
import { useAuthStore } from '@/stores/auth';
import { useChatConversations, useRenameChatConversation, useDeleteChatConversation } from '@/hooks/useChat';
import { useDiagnosisSessions, useDeleteDiagnosisSession } from '@/hooks/useDiagnosis';
import { useReports, useUploadReport } from '@/hooks/useReports';
import { useColors } from '@/hooks/useColors';

import { Spacing, FontWeight, BorderRadius } from '@/constants/theme';
import type { ColorPalette } from '@/constants/colors';

// ---------------------------------------------------------------------------
// Types
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
// Hooks
// ---------------------------------------------------------------------------

function useDynamicFonts() {
  const { fontScale, width } = useWindowDimensions();
  const base = width < 375 ? 14 : 16;
  return {
    item: base * fontScale,
    section: (base - 3) * fontScale,
    label: (base - 2) * fontScale,
    small: (base - 4) * fontScale,
  };
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SidebarContent({ navigation }: DrawerContentComponentProps) {
  const Colors = useColors();
  const fonts = useDynamicFonts();
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';

  const { data: chatData, isLoading: chatLoading } = useChatConversations(pid);
  const { data: dxData, isLoading: dxLoading } = useDiagnosisSessions(pid);
  const { data: reportData, isLoading: reportLoading } = useReports(pid);
  const uploadReport = useUploadReport(pid);

  const renameChat = useRenameChatConversation(pid);
  const deleteChat = useDeleteChatConversation(pid);
  const deleteDx = useDeleteDiagnosisSession(pid);

  const conversations = chatData?.items ?? [];
  const activeSessions = (dxData?.items ?? []).filter((s) => s.status === 'active');
  const reports = reportData?.items ?? [];

  const [menu, setMenu] = useState<ContextMenuState>(MENU_INITIAL);
  const dismissMenu = useCallback(() => setMenu(MENU_INITIAL), []);

  const close = () => navigation.closeDrawer();

  const navigateTo = (path: string) => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    close();
    const isDrawerRoute = path.startsWith('/(main)');
    setTimeout(() => {
      if (isDrawerRoute) router.navigate(path as never);
      else router.push(path as never);
    }, 150);
  };

  // ── Context menu openers ────────────────────────────────────────────────

  const openChatMenu = (id: string, title: string, x: number, y: number, w: number, h: number) => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setMenu({
      visible: true, title, x, y, width: w, height: h,
      actions: [
        {
          label: 'Rename', icon: 'pencil',
          onPress: () => {
            dismissMenu();
            setTimeout(() => {
              Alert.prompt('Rename Conversation', undefined, (t) => {
                if (t?.trim()) renameChat.mutate({ cid: id, topic: t.trim() });
              }, 'plain-text', title);
            }, 150);
          },
        },
        {
          label: 'Delete', icon: 'trash', destructive: true,
          onPress: () => {
            dismissMenu();
            setTimeout(() => {
              Alert.alert('Delete Conversation', 'This will also remove memories from this conversation.', [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Delete', style: 'destructive',
                  onPress: () => {
                    deleteChat.mutate(id);
                    if (pathname.includes(`/chat/${id}`)) router.navigate('/(main)' as never);
                  },
                },
              ]);
            }, 150);
          },
        },
      ],
    });
  };

  const openDxMenu = (id: string, title: string, x: number, y: number, w: number, h: number) => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setMenu({
      visible: true, title, x, y, width: w, height: h,
      actions: [
        {
          label: 'Delete', icon: 'trash', destructive: true,
          onPress: () => {
            dismissMenu();
            setTimeout(() => {
              Alert.alert('Delete Session', 'This will also remove memories from this session.', [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Delete', style: 'destructive',
                  onPress: () => {
                    deleteDx.mutate(id);
                    if (pathname.includes(`/diagnosis/${id}`)) router.navigate('/(main)' as never);
                  },
                },
              ]);
            }, 150);
          },
        },
      ],
    });
  };

  // ── Upload handler ──────────────────────────────────────────────────────

  const handleUpload = async () => {
    if (!pid) return;
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'],
      copyToCacheDirectory: true,
    });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    try {
      const report = await uploadReport.mutateAsync({
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType ?? 'application/pdf',
      });
      Alert.alert('Uploaded', 'Your report is being analyzed.');
      navigateTo(`/(main)/report/${report.id}`);
    } catch (err: unknown) {
      Alert.alert('Upload failed', err instanceof Error ? err.message : 'Unknown error');
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: Colors.surface, paddingTop: insets.top + Spacing.sm }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: Spacing.md, gap: Spacing.lg, paddingBottom: Spacing.lg }}
        showsVerticalScrollIndicator={false}
        scrollEnabled={!menu.visible}
      >
        {!activeProfile ? (
          <View style={{ paddingVertical: Spacing.xl, alignItems: 'center' }}>
            <Text style={{ fontSize: fonts.label, color: Colors.textMuted, textAlign: 'center' }}>
              Select a profile to see history
            </Text>
          </View>
        ) : (
          <>
            <SidebarSection title="Health Chats" iconName="chat-bubbles" loading={chatLoading} colors={Colors} fonts={fonts}>
              {conversations.length === 0 ? (
                <Text style={{ fontSize: fonts.label, color: Colors.textMuted, paddingVertical: Spacing.xs }}>
                  No conversations yet
                </Text>
              ) : (
                conversations.slice(0, 20).map((c, i) => (
                  <Animated.View key={c.id} entering={FadeInDown.delay(i * 30).duration(200)}>
                    <SidebarItem
                      title={c.topic || 'New conversation'}
                      active={pathname.includes(`/chat/${c.id}`)}
                      onPress={() => navigateTo(`/(main)/chat/${c.id}`)}
                      onLongPress={(x, y, w, h) => openChatMenu(c.id, c.topic || 'New conversation', x, y, w, h)}
                      colors={Colors}
                      fontSize={fonts.item}
                    />
                  </Animated.View>
                ))
              )}
            </SidebarSection>

            <SidebarSection title="Diagnoses" iconName="stethoscope" loading={dxLoading} colors={Colors} fonts={fonts}>
              {activeSessions.length === 0 ? (
                <Text style={{ fontSize: fonts.label, color: Colors.textMuted, paddingVertical: Spacing.xs }}>
                  No active sessions
                </Text>
              ) : (
                activeSessions.slice(0, 20).map((s, i) => (
                  <Animated.View key={s.id} entering={FadeInDown.delay(i * 30).duration(200)}>
                    <SidebarItem
                      title={s.chief_complaint}
                      active={pathname.includes(`/diagnosis/${s.id}`)}
                      onPress={() => navigateTo(`/(main)/diagnosis/${s.id}`)}
                      onLongPress={(x, y, w, h) => openDxMenu(s.id, s.chief_complaint, x, y, w, h)}
                      colors={Colors}
                      fontSize={fonts.item}
                    />
                  </Animated.View>
                ))
              )}
              <Pressable
                onPress={() => navigateTo('/(main)/diagnosis/past')}
                style={({ pressed }) => ({ paddingVertical: Spacing.sm, opacity: pressed ? 0.6 : 1 })}
              >
                <Text style={{ fontSize: fonts.small, color: Colors.textMuted }}>Past sessions ›</Text>
              </Pressable>
            </SidebarSection>

            <SidebarSection title="Reports" iconName="doc-search" loading={reportLoading} colors={Colors} fonts={fonts} onAction={handleUpload}>
              {reports.length === 0 ? (
                <Text style={{ fontSize: fonts.label, color: Colors.textMuted, paddingVertical: Spacing.xs }}>
                  No reports uploaded
                </Text>
              ) : (
                reports.slice(0, 20).map((r, i) => (
                  <Animated.View key={r.id} entering={FadeInDown.delay(i * 30).duration(200)}>
                    <SidebarItem
                      title={r.original_filename}
                      active={pathname.includes(`/report/${r.id}`)}
                      onPress={() => navigateTo(`/(main)/report/${r.id}`)}
                      colors={Colors}
                      fontSize={fonts.item}
                    />
                  </Animated.View>
                ))
              )}
            </SidebarSection>
          </>
        )}
      </ScrollView>

      {/* Footer */}
      <View
        style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          paddingHorizontal: Spacing.md, paddingTop: Spacing.lg,
          paddingBottom: insets.bottom + Spacing.lg,
        }}
      >
        <UserCapsule onPress={() => navigateTo('/settings')} fontSize={fonts.item} />
        <Pressable
          onPress={() => navigateTo('/(main)')}
          style={({ pressed }) => ({
            width: 48, height: 48, borderRadius: BorderRadius.full,
            backgroundColor: Colors.primary, alignItems: 'center', justifyContent: 'center',
            borderCurve: 'continuous', opacity: pressed ? 0.85 : 1,
          })}
        >
          <Icon name="plus" size={24} color={Colors.textInverse} />
        </Pressable>
      </View>

      {/* Context menu — full-screen Modal blocks ALL touches */}
      {menu.visible && (
        <ContextMenuOverlay
          menu={menu}
          colors={Colors}
          fonts={fonts}
          onDismiss={dismissMenu}
        />
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Context menu overlay (iOS context menu style)
// ---------------------------------------------------------------------------

// iOS context menu constants (reverse-engineered from iOS 17/18)
const MENU_ROW_HEIGHT = 44;
const MENU_RADIUS = 13;
const MENU_WIDTH = 250;
const MENU_GAP = 8;
const HIGHLIGHT_RADIUS = 12;

function ContextMenuOverlay({
  menu,
  colors: Colors,
  fonts,
  onDismiss,
}: {
  menu: ContextMenuState;
  colors: ColorPalette;
  fonts: ReturnType<typeof useDynamicFonts>;
  onDismiss: () => void;
}) {
  const { height: screenHeight } = useWindowDimensions();
  const menuCardHeight = menu.actions.length * MENU_ROW_HEIGHT + StyleSheet.hairlineWidth * (menu.actions.length - 1);
  const belowY = menu.y + menu.height + MENU_GAP;
  const aboveY = menu.y - MENU_GAP - menuCardHeight;
  // Flip above if menu would go off-screen
  const menuTop = belowY + menuCardHeight > screenHeight - 20 ? aboveY : belowY;

  return (
    <Modal transparent statusBarTranslucent animationType="none">
      <View style={StyleSheet.absoluteFill}>
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
              style={{ fontSize: fonts.item, color: Colors.text, fontWeight: FontWeight.semibold }}
              numberOfLines={1}
            >
              {menu.title}
            </Text>
          </BlurView>
        </Animated.View>

        {/* Menu card — iOS-style rounded blur card */}
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
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SidebarSection({
  title, iconName, loading, children, colors: Colors, fonts, onAction,
}: {
  title: string;
  iconName: 'chat-bubbles' | 'stethoscope' | 'doc-search';
  loading: boolean;
  children: React.ReactNode;
  colors: ColorPalette;
  fonts: ReturnType<typeof useDynamicFonts>;
  onAction?: () => void;
}) {
  return (
    <View style={{ gap: Spacing.xs }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingVertical: Spacing.xs }}>
        <Icon name={iconName} size={fonts.section} color={Colors.textMuted} />
        <Text
          style={{
            fontSize: fonts.section, fontWeight: FontWeight.semibold, color: Colors.textMuted,
            textTransform: 'uppercase', letterSpacing: 0.8, flex: 1,
          }}
        >
          {title}
        </Text>
        {loading && <ActivityIndicator size="small" color={Colors.textMuted} />}
        {onAction && (
          <Pressable onPress={onAction} style={({ pressed }) => ({ opacity: pressed ? 0.5 : 1, padding: Spacing.xs })}>
            <Icon name="plus" size={fonts.section} color={Colors.textMuted} />
          </Pressable>
        )}
      </View>
      {children}
    </View>
  );
}

function SidebarItem({
  title, active, onPress, onLongPress, colors: Colors, fontSize,
}: {
  title: string;
  active?: boolean;
  onPress: () => void;
  onLongPress?: (x: number, y: number, width: number, height: number) => void;
  colors: ColorPalette;
  fontSize: number;
}) {
  const viewRef = useRef<View>(null);

  const longPressRef = useRef(onLongPress);
  longPressRef.current = onLongPress;

  const handleLongPress = useCallback(() => {
    if (!longPressRef.current) return;
    viewRef.current?.measureInWindow((x, y, w, h) => {
      longPressRef.current!(x, y, w, h);
    });
  }, []);

  return (
    <View ref={viewRef} collapsable={false}>
      <Pressable
        onPress={onPress}
        onLongPress={handleLongPress}
        style={({ pressed }) => ({
          paddingVertical: Spacing.sm, paddingHorizontal: Spacing.sm,
          borderRadius: BorderRadius.sm, borderCurve: 'continuous',
          backgroundColor: active
            ? Colors.primary + '15'
            : pressed ? Colors.surfaceSecondary : 'transparent',
        })}
      >
        <Text
          style={{
            fontSize, color: active ? Colors.primary : Colors.text,
            fontWeight: active ? FontWeight.semibold : FontWeight.regular,
          }}
          numberOfLines={1}
        >
          {title}
        </Text>
      </Pressable>
    </View>
  );
}

function UserCapsule({ onPress, fontSize }: { onPress: () => void; fontSize: number }) {
  const Colors = useColors();
  const user = useAuthStore((s) => s.user);
  const email = user?.email ?? '';
  const fullName = user?.user_metadata?.full_name ?? email.split('@')[0] ?? 'User';
  const parts = fullName.trim().split(/\s+/);
  const displayName = parts.length > 1 ? parts[parts.length - 1] : parts[0];
  const initial = displayName.charAt(0).toUpperCase();

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => ({
        flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, height: 48,
        paddingLeft: Spacing.sm, paddingRight: Spacing.md,
        borderRadius: BorderRadius.full, borderCurve: 'continuous',
        backgroundColor: pressed ? Colors.surfaceSecondary : Colors.surface,
        borderWidth: 1, borderColor: Colors.border,
      })}
    >
      <View
        style={{
          width: 34, height: 34, borderRadius: BorderRadius.full,
          backgroundColor: Colors.primary + '20', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <Text style={{ fontSize, fontWeight: FontWeight.bold, color: Colors.primary }}>{initial}</Text>
      </View>
      <Text style={{ fontSize, fontWeight: FontWeight.medium, color: Colors.text }} numberOfLines={1}>
        {displayName}
      </Text>
    </Pressable>
  );
}
