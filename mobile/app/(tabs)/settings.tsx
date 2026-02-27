import { View, Text, Pressable, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import { Stack } from 'expo-router';
import { ScreenContainer } from '@/components/ScreenContainer';
import { useAuthStore } from '@/stores/auth';
import { signOut } from '@/services/auth';
import { Colors } from '@/constants/colors';
import { Spacing, FontSize, FontWeight, BorderRadius, Shadow } from '@/constants/theme';

interface SettingsRowProps {
  label: string;
  value?: string;
  onPress?: () => void;
  destructive?: boolean;
}

function SettingsRow({ label, value, onPress, destructive }: SettingsRowProps) {
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
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
    <>
      <Stack.Screen options={{ title: 'Settings', headerShown: true }} />
      <ScreenContainer contentStyle={{ gap: Spacing.lg }}>
        <Section title="Account">
          <SettingsRow label="Email" value={user?.email ?? '–'} />
        </Section>

        <Section title="App">
          <SettingsRow label="Notifications" value="Off" />
          <View style={{ height: 1, backgroundColor: Colors.border, marginLeft: Spacing.md }} />
          <SettingsRow label="App version" value="1.0.0" />
        </Section>

        <Section title="Legal">
          <SettingsRow label="Privacy Policy" onPress={() => {}} />
          <View style={{ height: 1, backgroundColor: Colors.border, marginLeft: Spacing.md }} />
          <SettingsRow label="Terms of Service" onPress={() => {}} />
        </Section>

        <Section title="Danger zone">
          <SettingsRow label="Sign out" onPress={handleSignOut} destructive />
        </Section>
      </ScreenContainer>
    </>
  );
}
