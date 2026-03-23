import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  KeyboardAvoidingView,
  ScrollView,
  Alert,
} from 'react-native';
import { Link, useRouter } from 'expo-router';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { signUpWithEmail } from '@/services/auth';
import { Copy } from '@/constants/branding';

export default function SignupScreen() {
  const Colors = useColors();
  const Shadow = useShadow();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSignup = async () => {
    if (!email || !password) return;
    if (password !== confirm) {
      Alert.alert('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      await signUpWithEmail(email, password);
      Alert.alert('Check your email', 'We sent you a confirmation link.', [
        { text: 'OK', onPress: () => router.replace('/(auth)/login') },
      ]);
    } catch (err: unknown) {
      Alert.alert('Sign up failed', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: Colors.background }}
      behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={{
          flexGrow: 1,
          justifyContent: 'center',
          padding: Spacing.xl,
          gap: Spacing.md,
        }}
      >
        {/* Header */}
        <View style={{ marginBottom: Spacing.lg }}>
          <Text style={{ fontSize: FontSize.xxxl, fontWeight: FontWeight.bold, color: Colors.text }}>
            {Copy.signup.title}
          </Text>
          <Text style={{ fontSize: FontSize.md, color: Colors.textSecondary, marginTop: Spacing.xs }}>
            {Copy.signup.subtitle}
          </Text>
        </View>

        {/* Email */}
        <View style={{ gap: Spacing.xs }}>
          <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.medium, color: Colors.text }}>
            Email
          </Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="you@example.com"
            placeholderTextColor={Colors.textMuted}
            autoCapitalize="none"
            keyboardType="email-address"
            textContentType="emailAddress"
            style={{
              backgroundColor: Colors.surface,
              borderWidth: 1,
              borderColor: Colors.border,
              borderRadius: BorderRadius.md,
              padding: Spacing.md,
              fontSize: FontSize.md,
              color: Colors.text,
            }}
          />
        </View>

        {/* Password */}
        <View style={{ gap: Spacing.xs }}>
          <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.medium, color: Colors.text }}>
            Password
          </Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Min 8 characters"
            placeholderTextColor={Colors.textMuted}
            secureTextEntry
            textContentType="newPassword"
            style={{
              backgroundColor: Colors.surface,
              borderWidth: 1,
              borderColor: Colors.border,
              borderRadius: BorderRadius.md,
              padding: Spacing.md,
              fontSize: FontSize.md,
              color: Colors.text,
            }}
          />
        </View>

        {/* Confirm */}
        <View style={{ gap: Spacing.xs }}>
          <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.medium, color: Colors.text }}>
            Confirm password
          </Text>
          <TextInput
            value={confirm}
            onChangeText={setConfirm}
            placeholder="Re-enter password"
            placeholderTextColor={Colors.textMuted}
            secureTextEntry
            textContentType="newPassword"
            style={{
              backgroundColor: Colors.surface,
              borderWidth: 1,
              borderColor: Colors.border,
              borderRadius: BorderRadius.md,
              padding: Spacing.md,
              fontSize: FontSize.md,
              color: Colors.text,
            }}
          />
        </View>

        {/* Submit */}
        <Pressable
          onPress={handleSignup}
          disabled={loading}
          style={({ pressed }) => ({
            backgroundColor: loading ? Colors.primaryLight : Colors.primary,
            borderRadius: BorderRadius.md,
            padding: Spacing.md,
            alignItems: 'center',
            opacity: pressed ? 0.9 : 1,
            marginTop: Spacing.xs,
            ...Shadow.sm,
          })}
        >
          <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.textInverse }}>
            {loading ? 'Creating account…' : 'Create account'}
          </Text>
        </Pressable>

        {/* Login link */}
        <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: Spacing.sm }}>
          <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary }}>
            Already have an account?{' '}
          </Text>
          <Link href="/(auth)/login" asChild>
            <Pressable>
              <Text style={{ fontSize: FontSize.sm, color: Colors.primary, fontWeight: FontWeight.semibold }}>
                Sign in
              </Text>
            </Pressable>
          </Link>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
