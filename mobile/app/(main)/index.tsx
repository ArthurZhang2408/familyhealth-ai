import { useState } from 'react';
import { View, Text, KeyboardAvoidingView, Alert } from 'react-native';
import { useRouter, Stack } from 'expo-router';
import Animated, { FadeIn, FadeInUp } from 'react-native-reanimated';
import { Icon } from '@/components/Icon';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { ChatInput } from '@/components/ChatInput';
import { ModeToggle, type ConversationMode } from '@/components/ModeToggle';
import { useProfileStore } from '@/stores/profile';
import { useAttachMenu, type Attachment } from '@/hooks/useAttachMenu';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { setPendingSend } from '@/services/pendingSend';

export default function NewConversationScreen() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
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

    // Navigate immediately — the target screen handles the streaming send
    setPendingSend(text || ' ', files);
    if (mode === 'chat') {
      router.navigate('/(main)/chat/new' as never);
    } else {
      router.navigate('/(main)/diagnosis/new' as never);
    }
  };

  return (
    <NoProfileGuard>
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
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.xl }}>
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
              fontSize: FontSize.xl,
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
    </NoProfileGuard>
  );
}
