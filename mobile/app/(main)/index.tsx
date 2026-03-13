import { useState } from 'react';
import { View, Text, Pressable, KeyboardAvoidingView, ActivityIndicator } from 'react-native';
import { useRouter, Stack } from 'expo-router';
import Animated, { FadeIn, FadeInUp } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { ChatInput } from '@/components/ChatInput';
import { ModeToggle, type ConversationMode } from '@/components/ModeToggle';
import { useProfileStore } from '@/stores/profile';
import { useProfiles } from '@/hooks/useProfiles';
import { useAttachMenu, type Attachment } from '@/hooks/useAttachMenu';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { setPendingSend } from '@/services/pendingSend';

export default function NewConversationScreen() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const hydrated = useProfileStore((s) => s._hydrated);
  const { data: profilesData } = useProfiles();
  const pid = activeProfile?.id ?? '';

  const [input, setInput] = useState('');
  const [mode, setMode] = useState<ConversationMode>('chat');
  const [pendingAttachment, setPendingAttachment] = useState<Attachment | null>(null);

  const handleAttach = useAttachMenu((attachment) => setPendingAttachment(attachment));

  const isBusy = false;

  const handleSend = async () => {
    const text = input.trim();
    if ((!text && !pendingAttachment) || isBusy || !pid) return;
    setInput('');
    const files = pendingAttachment ? [pendingAttachment] : undefined;
    setPendingAttachment(null);

    // Navigate immediately — the target screen handles the streaming send.
    // Use a unique ID each time (not just "new") so the Drawer navigator
    // is forced to update useLocalSearchParams — it caches params for
    // chat/[cid] and won't update if the value is the same as last time.
    setPendingSend(text || ' ', files);
    const ts = Date.now();
    if (mode === 'chat') {
      router.navigate({ pathname: '/(main)/chat/[cid]', params: { cid: `new-${ts}` } } as never);
    } else {
      router.navigate({ pathname: '/(main)/diagnosis/[sid]', params: { sid: `new-${ts}` } } as never);
    }
  };

  // New account — no profiles exist yet
  if (!activeProfile) {
    // Still loading (hydration or API)
    if (!hydrated || !profilesData) {
      return (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.background }}>
          <ActivityIndicator size="small" color={Colors.textMuted} />
        </View>
      );
    }
    // Genuinely no profiles — welcome state
    if (profilesData.items.length === 0) {
      return (
        <>
          <Stack.Screen options={{}} />
          <View style={{ flex: 1, alignItems: 'center', backgroundColor: Colors.background, padding: Spacing.xl }}>
            <View style={{ flex: 1 }} />
            <Animated.View entering={FadeIn.duration(500)} style={{ alignItems: 'center' }}>
              <View
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: BorderRadius.lg,
                  borderCurve: 'continuous',
                  backgroundColor: Colors.primary + '12',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: Spacing.md,
                }}
              >
                <Icon name="heart-clipboard" size={28} color={Colors.primary} />
              </View>
            </Animated.View>
            <Animated.Text
              entering={FadeInUp.delay(120).duration(350)}
              style={{
                fontSize: FontSize.xxl,
                fontWeight: FontWeight.bold,
                color: Colors.text,
                textAlign: 'center',
              }}
            >
              Welcome
            </Animated.Text>
            <Animated.Text
              entering={FadeInUp.delay(240).duration(350)}
              style={{
                fontSize: FontSize.md,
                color: Colors.textSecondary,
                textAlign: 'center',
                marginTop: Spacing.sm,
                lineHeight: 22,
                maxWidth: 280,
              }}
            >
              Your AI health companion for the whole family. Create a profile to get started.
            </Animated.Text>
            <Animated.View entering={FadeInUp.delay(400).duration(350)}>
              <Pressable
                onPress={() => {
                  if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  router.push('/profile/new');
                }}
                style={({ pressed }) => ({
                  marginTop: Spacing.xl,
                  backgroundColor: Colors.primary,
                  borderRadius: BorderRadius.md,
                  borderCurve: 'continuous',
                  paddingHorizontal: Spacing.xl,
                  paddingVertical: Spacing.md,
                  opacity: pressed ? 0.85 : 1,
                })}
              >
                <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.textInverse }}>
                  Get started
                </Text>
              </Pressable>
            </Animated.View>
            <View style={{ flex: 2 }} />
          </View>
        </>
      );
    }
    // Profiles exist but auto-select hasn't fired yet — brief loading
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.background }}>
        <ActivityIndicator size="small" color={Colors.textMuted} />
      </View>
    );
  }

  return (
    <>
      <Stack.Screen
        options={{
          headerRight: () => (
            <ModeToggle
              mode={mode}
              onToggle={() => setMode((m) => (m === 'chat' ? 'diagnosis' : 'chat'))}
            />
          ),
        }}
      />
      <KeyboardAvoidingView
        style={{ flex: 1, backgroundColor: Colors.background }}
        behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        <View style={{ flex: 1, alignItems: 'center', padding: Spacing.xl }}>
          <View style={{ flex: 1 }} />
          <Animated.View entering={FadeIn.duration(400)} style={{ alignItems: 'center' }}>
            <View
              style={{
                width: 56,
                height: 56,
                borderRadius: BorderRadius.lg,
                borderCurve: 'continuous',
                backgroundColor: Colors.primary + '12',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: Spacing.md,
              }}
            >
              <Icon name="heart-clipboard" size={28} color={Colors.primary} />
            </View>
          </Animated.View>
          <Animated.Text
            entering={FadeInUp.delay(100).duration(300)}
            style={{
              fontSize: FontSize.xxl,
              fontWeight: FontWeight.bold,
              color: Colors.text,
              textAlign: 'center',
            }}
          >
            {mode === 'chat' ? 'Health Chat' : 'AI Diagnosis'}
          </Animated.Text>
          <Animated.Text
            entering={FadeInUp.delay(200).duration(300)}
            style={{
              fontSize: FontSize.md,
              color: Colors.textSecondary,
              textAlign: 'center',
              marginTop: Spacing.sm,
              lineHeight: 22,
              maxWidth: 300,
            }}
          >
            {mode === 'chat'
              ? 'Ask any health question about medications, conditions, or test results.'
              : 'Describe symptoms for a structured AI-assisted assessment.'}
          </Animated.Text>
          <View style={{ flex: 2 }} />
        </View>

        <ChatInput
          value={input}
          onChangeText={setInput}
          onSend={handleSend}
          isBusy={isBusy}
          onAttach={handleAttach}
          attachment={pendingAttachment}
          onRemoveAttachment={() => setPendingAttachment(null)}
          placeholder={
            mode === 'chat'
              ? 'Ask a health question…'
              : 'Describe your symptoms…'
          }
        />
      </KeyboardAvoidingView>
    </>
  );
}
