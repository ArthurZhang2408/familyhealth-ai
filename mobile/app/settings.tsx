import { View, Text, Pressable, Alert, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuthStore } from '@/stores/auth';
import { signOut } from '@/services/auth';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { ColorPalette } from '@/constants/colors';

interface SettingsRowProps {
  label: string;
  value?: string;
  onPress?: () => void;
  destructive?: boolean;
  colors: ColorPalette;
}

function SettingsRow({ label, value, onPress, destructive, colors: Colors }: SettingsRowProps) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => ({
        backgroundColor: Colors.surface,
        padding: Spacing.md,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        opacity: pressed && onPress ? 0.7 : 1,
      })}
    >
      <Text
        style={{
          fontSize: FontSize.md,
          color: destructive ? Colors.error : Colors.text,
        }}
      >
        {label}
      </Text>
      {value && (
        <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary }}>{value}</Text>
      )}
    </Pressable>
  );
}

function Section({ title, children, colors: Colors, shadow: Shadow }: { title: string; children: React.ReactNode; colors: ColorPalette; shadow: ReturnType<typeof useShadow> }) {
  return (
    <View>
      <Text
        style={{
          fontSize: FontSize.xs,
          fontWeight: FontWeight.semibold,
          color: Colors.textMuted,
          textTransform: 'uppercase',
          letterSpacing: 0.8,
          paddingHorizontal: Spacing.md,
          paddingBottom: Spacing.xs,
        }}
      >
        {title}
      </Text>
      <View
        style={{
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          overflow: 'hidden',
          borderWidth: 1,
          borderColor: Colors.border,
          ...Shadow.sm,
        }}
      >
        {children}
      </View>
    </View>
  );
}

export default function SettingsScreen() {
  const Colors = useColors();
  const Shadow = useShadow();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const handleSignOut = () => {
    Alert.alert('Sign out', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          await signOut();
          router.replace('/(auth)/login');
        },
      },
    ]);
  };

  return (
    <ScrollView
      contentContainerStyle={{ padding: Spacing.md, gap: Spacing.lg, paddingBottom: Spacing.xxl }}
      style={{ flex: 1, backgroundColor: Colors.surface }}
    >
      <Section title="Account" colors={Colors} shadow={Shadow}>
        <SettingsRow label="Email" value={user?.email ?? '–'} colors={Colors} />
      </Section>

      <Section title="App" colors={Colors} shadow={Shadow}>
        <SettingsRow label="Notifications" value="Off" colors={Colors} />
        <View style={{ height: 1, backgroundColor: Colors.border, marginLeft: Spacing.md }} />
        <SettingsRow label="App version" value="1.0.0" colors={Colors} />
      </Section>

      <Section title="Legal" colors={Colors} shadow={Shadow}>
        <SettingsRow label="Privacy Policy" onPress={() => {}} colors={Colors} />
        <View style={{ height: 1, backgroundColor: Colors.border, marginLeft: Spacing.md }} />
        <SettingsRow label="Terms of Service" onPress={() => {}} colors={Colors} />
      </Section>

      <Section title="Danger zone" colors={Colors} shadow={Shadow}>
        <SettingsRow label="Sign out" onPress={handleSignOut} destructive colors={Colors} />
      </Section>
    </ScrollView>
  );
}
