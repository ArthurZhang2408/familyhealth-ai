import { useState, useEffect, useCallback, useRef } from 'react';
import { View, Text, Pressable, Keyboard, ActivityIndicator } from 'react-native';
import { useRouter, Stack } from 'expo-router';
import Animated from 'react-native-reanimated';

import * as Haptics from 'expo-haptics';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { useFocusEffect } from '@react-navigation/native';
import { ChatInput } from '@/components/ChatInput';
import { ModeToggle, type ConversationMode } from '@/components/ModeToggle';
import { PromptSuggestions } from '@/components/PromptSuggestions';
import { AnimatedSalkIcon } from '@/components/AnimatedSalkIcon';
import { usePromptSuggestions } from '@/hooks/usePromptSuggestions';
import { useProfileStore } from '@/stores/profile';
import { useProfiles } from '@/hooks/useProfiles';
import { useAttachMenu, type Attachment } from '@/hooks/useAttachMenu';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { setPendingSend } from '@/services/pendingSend';
import { enterSlideUp } from '@/constants/animations';
import { useNavSource } from '@/services/navigationSource';
import { Copy } from '@/constants/branding';
import type { Relationship } from '@/types/api';

/** Familiar address: "Dad", "Mom", "Grandma" for gendered relations; profile name otherwise */
function familiarName(name: string, rel: Relationship): string {
  switch (rel) {
    case 'father': return 'Dad';
    case 'mother': return 'Mom';
    case 'grandfather': return 'Grandpa';
    case 'grandmother': return 'Grandma';
    default: return name;
  }
}

function greeting(name: string, rel: Relationship, mode: 'chat' | 'diagnosis') {
  const who = familiarName(name, rel);
  if (rel === 'self') {
    return {
      title: mode === 'chat' ? `What's on your mind, ${name}?` : `What's going on, ${name}?`,
      subtitle: mode === 'chat'
        ? 'Ask anything about your health, meds, or results.'
        : 'Describe what you\'re feeling for an assessment.',
    };
  }
  const isKid = ['child', 'son', 'daughter'].includes(rel);
  return {
    title: mode === 'chat'
      ? isKid ? `How's ${who} feeling?` : `How's ${who} doing?`
      : `What's going on with ${who}?`,
    subtitle: mode === 'chat'
      ? `Ask about ${who}'s health, medications, or conditions.`
      : `Describe ${who}'s symptoms for an assessment.`,
  };
}

export default function NewConversationScreen() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const hydrated = useProfileStore((s) => s._hydrated);
  const { data: profilesData } = useProfiles();
  const pid = activeProfile?.id ?? '';

  const pendingMode = useNavSource((s) => s.pendingMode);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<ConversationMode>('chat');
  const [pendingAttachment, setPendingAttachment] = useState<Attachment | null>(null);

  useEffect(() => {
    if (pendingMode) {
      setMode(pendingMode);
      useNavSource.getState().setPendingMode(null);
    }
  }, [pendingMode]);

  const handleAttach = useAttachMenu((attachment) => setPendingAttachment(attachment));

  const busyRef = useRef(false);
  const [isBusy, setIsBusy] = useState(false);

  // Reset busy guard when screen regains focus (navigated back from session)
  useFocusEffect(useCallback(() => { busyRef.current = false; setIsBusy(false); }, []));

  const { suggestions, isLoading: suggestionsLoading } = usePromptSuggestions(mode);

  const doSend = useCallback((text: string, files?: Attachment[]) => {
    if ((!text && !files) || busyRef.current || !pid) return;
    busyRef.current = true;
    setIsBusy(true);
    Keyboard.dismiss();
    setPendingSend(text || ' ', files);
    const ts = Date.now();
    if (mode === 'chat') {
      router.navigate({ pathname: '/(main)/chat/[cid]', params: { cid: `new-${ts}` } } as never);
    } else {
      router.navigate({ pathname: '/(main)/diagnosis/[sid]', params: { sid: `new-${ts}` } } as never);
    }
  }, [pid, mode, router]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    const files = pendingAttachment ? [pendingAttachment] : undefined;
    setInput('');
    setPendingAttachment(null);
    doSend(text, files);
  }, [input, pendingAttachment, doSend]);

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
            <View style={{ marginBottom: Spacing.md }}>
              <AnimatedSalkIcon size={64} />
            </View>
            <Animated.Text
              entering={enterSlideUp(120)}
              style={{
                fontSize: FontSize.xxl,
                fontWeight: FontWeight.bold,
                color: Colors.text,
                textAlign: 'center',
              }}
            >
              {Copy.welcome.title}
            </Animated.Text>
            <Animated.Text
              entering={enterSlideUp(240)}
              style={{
                fontSize: FontSize.md,
                color: Colors.textSecondary,
                textAlign: 'center',
                marginTop: Spacing.sm,
                lineHeight: 22,
                maxWidth: 280,
              }}
            >
              {Copy.welcome.subtitle}
            </Animated.Text>
            <Animated.View entering={enterSlideUp(400)}>
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
                  {Copy.welcome.cta}
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

  const greet = activeProfile
    ? greeting(activeProfile.name, activeProfile.relationship, mode)
    : { title: mode === 'chat' ? Copy.home.chat.title : Copy.home.diagnosis.title,
        subtitle: mode === 'chat' ? Copy.home.chat.subtitle : Copy.home.diagnosis.subtitle };

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
        <Pressable style={{ flex: 1, alignItems: 'center', padding: Spacing.xl }} onPress={Keyboard.dismiss}>
          <View style={{ flex: 1 }} />
          <View style={{ marginBottom: Spacing.md }}>
            <AnimatedSalkIcon size={56} key={`${pid}-${mode}`} />
          </View>
          <Animated.Text
            entering={enterSlideUp(120)}
            style={{
              fontSize: FontSize.xxl,
              fontWeight: FontWeight.bold,
              color: Colors.text,
              textAlign: 'center',
            }}
          >
            {greet.title}
          </Animated.Text>
          <Animated.Text
            entering={enterSlideUp(240)}
            style={{
              fontSize: FontSize.md,
              color: Colors.textSecondary,
              textAlign: 'center',
              marginTop: Spacing.sm,
              lineHeight: 22,
              maxWidth: 300,
            }}
          >
            {greet.subtitle}
          </Animated.Text>
          <Text
            style={{
              fontSize: FontSize.xs,
              color: Colors.textMuted,
              textAlign: 'center',
              marginTop: Spacing.xs,
            }}
          >
            {mode === 'chat' ? 'Ask health questions' : 'Get a structured assessment'}
          </Text>
          <View style={{ flex: 2 }} />
        </Pressable>

        <View style={{ marginBottom: Spacing.sm }}>
          <PromptSuggestions
            suggestions={suggestions}
            isLoading={suggestionsLoading}
            onSelectPrompt={(text) => doSend(text)}
            onNavigateSession={(sessionId, type) => {
              setIsBusy(true);
              Keyboard.dismiss();
              if (type === 'chat') {
                router.navigate({ pathname: '/(main)/chat/[cid]', params: { cid: sessionId } } as never);
              } else {
                router.navigate({ pathname: '/(main)/diagnosis/[sid]', params: { sid: sessionId } } as never);
              }
            }}
            disabled={isBusy}
          />
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
              ? Copy.home.chat.placeholder
              : Copy.home.diagnosis.placeholder
          }
        />
      </KeyboardAvoidingView>
    </>
  );
}
