import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  KeyboardAvoidingView,
  Alert,
} from 'react-native';
import { Link, useRouter } from 'expo-router';
import { useColors } from '@/hooks/useColors';
import { AnimatedSalkIcon } from '@/components/AnimatedSalkIcon';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { signInWithEmail, signInWithGoogle, signInWithApple } from '@/services/auth';
import { AppName, AppTagline, LoginIcon } from '@/constants/branding';

export default function LoginScreen() {
  const Colors = useColors();
  const Shadow = useShadow();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleEmailLogin = async () => {
    if (!email || !password) return;
    setLoading(true);
    try {
      await signInWithEmail(email, password);
      router.replace('/(main)');
    } catch (err: unknown) {
      Alert.alert('Sign in failed', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    try {
      await signInWithGoogle();
    } catch (err: unknown) {
      Alert.alert('Google sign in failed', err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const handleAppleLogin = async () => {
    try {
      await signInWithApple();
      router.replace('/(main)');
    } catch (err: unknown) {
      Alert.alert('Apple sign in failed', err instanceof Error ? err.message : 'Unknown error');
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: Colors.background }}
      behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined}
    >
      <View
        style={{
          flex: 1,
          justifyContent: 'center',
          padding: Spacing.xl,
          gap: Spacing.md,
        }}
      >
        {/* Header */}
        <View style={{ alignItems: 'center', marginBottom: Spacing.lg }}>
          <AnimatedSalkIcon size={LoginIcon.containerSize} />
          <Text
            style={{
              fontSize: FontSize.xxxl,
              fontWeight: FontWeight.bold,
              color: Colors.text,
            }}
          >
            {AppName}
          </Text>
          <Text
            style={{
              fontSize: FontSize.md,
              color: Colors.textSecondary,
              marginTop: Spacing.xs,
              textAlign: 'center',
            }}
          >
            {AppTagline}
          </Text>
        </View>

        {/* Email field */}
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

        {/* Password field */}
        <View style={{ gap: Spacing.xs }}>
          <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.medium, color: Colors.text }}>
            Password
          </Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor={Colors.textMuted}
            secureTextEntry
            textContentType="password"
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

        {/* Sign in button */}
        <Pressable
          onPress={handleEmailLogin}
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
            {loading ? 'Signing in…' : 'Sign in'}
          </Text>
        </Pressable>

        {/* Divider */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.md }}>
          <View style={{ flex: 1, height: 1, backgroundColor: Colors.border }} />
          <Text style={{ fontSize: FontSize.sm, color: Colors.textMuted }}>or</Text>
          <View style={{ flex: 1, height: 1, backgroundColor: Colors.border }} />
        </View>

        {/* OAuth buttons */}
        <Pressable
          onPress={handleGoogleLogin}
          style={({ pressed }) => ({
            backgroundColor: Colors.surface,
            borderWidth: 1,
            borderColor: Colors.border,
            borderRadius: BorderRadius.md,
            padding: Spacing.md,
            alignItems: 'center',
            opacity: pressed ? 0.85 : 1,
          })}
        >
          <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.medium, color: Colors.text }}>
            Continue with Google
          </Text>
        </Pressable>

        {process.env.EXPO_OS === 'ios' && (
          <Pressable
            onPress={handleAppleLogin}
            style={({ pressed }) => ({
              backgroundColor: Colors.text,
              borderRadius: BorderRadius.md,
              padding: Spacing.md,
              alignItems: 'center',
              opacity: pressed ? 0.85 : 1,
            })}
          >
            <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.medium, color: Colors.textInverse }}>
              Continue with Apple
            </Text>
          </Pressable>
        )}

        {/* Sign up link */}
        <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: Spacing.sm }}>
          <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary }}>
            Don't have an account?{' '}
          </Text>
          <Link href="/(auth)/signup" asChild>
            <Pressable>
              <Text style={{ fontSize: FontSize.sm, color: Colors.primary, fontWeight: FontWeight.semibold }}>
                Sign up
              </Text>
            </Pressable>
          </Link>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
