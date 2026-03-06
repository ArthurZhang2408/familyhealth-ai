import { View, Text, Pressable, ScrollView, ActivityIndicator, Alert, useWindowDimensions } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { Icon } from '@/components/Icon';
import { useRouter, usePathname } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { DrawerContentComponentProps } from '@react-navigation/drawer';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { useProfileStore } from '@/stores/profile';
import { useAuthStore } from '@/stores/auth';
import { useChatConversations } from '@/hooks/useChat';
import { useDiagnosisSessions } from '@/hooks/useDiagnosis';
import { useReports, useUploadReport } from '@/hooks/useReports';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontWeight, BorderRadius } from '@/constants/theme';
import type { ColorPalette } from '@/constants/colors';

/** Dynamic font sizing based on screen width — respects system text scaling */
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

  const conversations = chatData?.items ?? [];
  const activeSessions = (dxData?.items ?? []).filter((s) => s.status === 'active');
  const reports = reportData?.items ?? [];

  const close = () => navigation.closeDrawer();

  const navigateTo = (path: string) => {
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    close();
    // Drawer doesn't support push (it falls through to the parent Stack).
    // Use navigate for intra-Drawer routes, push for root-level modals.
    const isDrawerRoute = path.startsWith('/(main)');
    setTimeout(() => {
      if (isDrawerRoute) {
        router.navigate(path as never);
      } else {
        router.push(path as never);
      }
    }, 150);
  };

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

  return (
    <View
      style={{
        flex: 1,
        backgroundColor: Colors.surface,
        paddingTop: insets.top + Spacing.sm,
      }}
    >
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: Spacing.md, gap: Spacing.lg, paddingBottom: Spacing.lg }}
        showsVerticalScrollIndicator={false}
      >
        {!activeProfile ? (
          <View style={{ paddingVertical: Spacing.xl, alignItems: 'center' }}>
            <Text style={{ fontSize: fonts.label, color: Colors.textMuted, textAlign: 'center' }}>
              Select a profile to see history
            </Text>
          </View>
        ) : (
          <>
            {/* Health Chats */}
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
                      colors={Colors}
                      fontSize={fonts.item}
                    />
                  </Animated.View>
                ))
              )}
            </SidebarSection>

            {/* Diagnoses — active only */}
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
                      colors={Colors}
                      fontSize={fonts.item}
                    />
                  </Animated.View>
                ))
              )}
              {/* Past sessions link */}
              <Pressable
                onPress={() => navigateTo('/(main)/diagnosis/past')}
                style={({ pressed }) => ({
                  paddingVertical: Spacing.sm,
                  opacity: pressed ? 0.6 : 1,
                })}
              >
                <Text style={{ fontSize: fonts.small, color: Colors.textMuted }}>
                  Past sessions ›
                </Text>
              </Pressable>
            </SidebarSection>

            {/* Reports */}
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

      {/* Footer — user capsule + new conversation, centered on same row */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: Spacing.md,
          paddingTop: Spacing.lg,
          paddingBottom: insets.bottom + Spacing.lg,
        }}
      >
        <UserCapsule onPress={() => navigateTo('/settings')} fontSize={fonts.item} />
        <Pressable
          onPress={() => navigateTo('/(main)')}
          style={({ pressed }) => ({
            width: 48,
            height: 48,
            borderRadius: BorderRadius.full,
            backgroundColor: Colors.primary,
            alignItems: 'center',
            justifyContent: 'center',
            borderCurve: 'continuous',
            opacity: pressed ? 0.85 : 1,
          })}
        >
          <Icon name="plus" size={24} color={Colors.textInverse} />
        </Pressable>
      </View>
    </View>
  );
}

function SidebarSection({
  title,
  iconName,
  loading,
  children,
  colors: Colors,
  fonts,
  onAction,
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
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.sm,
          paddingVertical: Spacing.xs,
        }}
      >
        <Icon name={iconName} size={fonts.section} color={Colors.textMuted} />
        <Text
          style={{
            fontSize: fonts.section,
            fontWeight: FontWeight.semibold,
            color: Colors.textMuted,
            textTransform: 'uppercase',
            letterSpacing: 0.8,
            flex: 1,
          }}
        >
          {title}
        </Text>
        {loading && <ActivityIndicator size="small" color={Colors.textMuted} />}
        {onAction && (
          <Pressable
            onPress={onAction}
            style={({ pressed }) => ({ opacity: pressed ? 0.5 : 1, padding: Spacing.xs })}
          >
            <Icon name="plus" size={fonts.section} color={Colors.textMuted} />
          </Pressable>
        )}
      </View>
      {children}
    </View>
  );
}

function SidebarItem({
  title,
  active,
  onPress,
  colors: Colors,
  fontSize,
}: {
  title: string;
  active?: boolean;
  onPress: () => void;
  colors: ColorPalette;
  fontSize: number;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => ({
        paddingVertical: Spacing.sm,
        paddingHorizontal: Spacing.sm,
        borderRadius: BorderRadius.sm,
        borderCurve: 'continuous',
        backgroundColor: active
          ? Colors.primary + '15'
          : pressed
            ? Colors.surfaceSecondary
            : 'transparent',
      })}
    >
      <Text
        style={{
          fontSize,
          color: active ? Colors.primary : Colors.text,
          fontWeight: active ? FontWeight.semibold : FontWeight.regular,
        }}
        numberOfLines={1}
      >
        {title}
      </Text>
    </Pressable>
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
        flexDirection: 'row',
        alignItems: 'center',
        gap: Spacing.sm,
        height: 48,
        paddingLeft: Spacing.sm,
        paddingRight: Spacing.md,
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous',
        backgroundColor: pressed ? Colors.surfaceSecondary : Colors.surface,
        borderWidth: 1,
        borderColor: Colors.border,
      })}
    >
      <View
        style={{
          width: 34,
          height: 34,
          borderRadius: BorderRadius.full,
          backgroundColor: Colors.primary + '20',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Text style={{ fontSize: fontSize, fontWeight: FontWeight.bold, color: Colors.primary }}>
          {initial}
        </Text>
      </View>
      <Text
        style={{ fontSize: fontSize, fontWeight: FontWeight.medium, color: Colors.text }}
        numberOfLines={1}
      >
        {displayName}
      </Text>
    </Pressable>
  );
}
