import { useState } from 'react';
import { View, Text, KeyboardAvoidingView, Alert } from 'react-native';
import { useRouter, Stack } from 'expo-router';
import Animated, { FadeIn, FadeInUp } from 'react-native-reanimated';
import * as DocumentPicker from 'expo-document-picker';
import { Icon } from '@/components/Icon';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { ChatInput } from '@/components/ChatInput';
import { ModeToggle, type ConversationMode } from '@/components/ModeToggle';
import { useProfileStore } from '@/stores/profile';
import { useCreateDiagnosisSession } from '@/hooks/useDiagnosis';
import { useSendChatMessage } from '@/hooks/useChat';
import { useUploadReport } from '@/hooks/useReports';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

export default function NewConversationScreen() {
  const Colors = useColors();
  const router = useRouter();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';

  const [input, setInput] = useState('');
  const [mode, setMode] = useState<ConversationMode>('chat');

  const sendChat = useSendChatMessage(pid);
  const createDiagnosis = useCreateDiagnosisSession(pid);
  const uploadReport = useUploadReport(pid);

  const isBusy = sendChat.isPending || createDiagnosis.isPending;

  const handleSend = async () => {
    if (!input.trim() || isBusy || !pid) return;
    const text = input.trim();
    setInput('');

    try {
      if (mode === 'chat') {
        const response = await sendChat.mutateAsync({ content: text });
        router.replace(`/(main)/chat/${response.message.conversation_id}`);
      } else {
        const session = await createDiagnosis.mutateAsync(text);
        router.replace(`/(main)/diagnosis/${session.id}`);
      }
    } catch (err: unknown) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Something went wrong');
      setInput(text);
    }
  };

  const handleAttach = async () => {
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
      router.push(`/(main)/report/${report.id}`);
    } catch (err: unknown) {
      Alert.alert('Upload failed', err instanceof Error ? err.message : 'Unknown error');
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
