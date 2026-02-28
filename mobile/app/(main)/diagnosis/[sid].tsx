import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { View, Text, Pressable, FlatList, KeyboardAvoidingView } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { ChatBubble, TypingIndicator } from '@/components/ChatBubble';
import { ChatInput } from '@/components/ChatInput';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Icon } from '@/components/Icon';
import Animated, { FadeIn } from 'react-native-reanimated';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { useProfileStore } from '@/stores/profile';
import { useDiagnosisSession, useSendDiagnosisMessage } from '@/hooks/useDiagnosis';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

interface LocalMessage {
  role: 'user' | 'assistant';
  content: string;
  id: string;
}

export default function DiagnosisScreen() {
  const Colors = useColors();
  const { sid } = useLocalSearchParams<{ sid: string }>();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';

  const PHASE_LABELS = useMemo(() => ({
    gathering: { label: 'Gathering info', color: Colors.info },
    analyzing: { label: 'Analyzing', color: Colors.warning },
    complete: { label: 'Complete', color: Colors.success },
  } as Record<string, { label: string; color: string }>), [Colors]);

  const [pendingMessages, setPendingMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState('');
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);

  const { data: session, isLoading, error, refetch } = useDiagnosisSession(pid, sid);
  const sendMessage = useSendDiagnosisMessage(pid, sid);

  // Clear pending once server data catches up (prevents duplicates on refetch)
  const serverMsgCount = session?.messages?.length ?? 0;
  useEffect(() => {
    if (serverMsgCount > 0 && pendingMessages.length > 0) {
      setPendingMessages([]);
    }
  }, [serverMsgCount, pendingMessages.length]);

  // Merge server messages + locally sent messages
  const serverMessages: LocalMessage[] = (session?.messages ?? []).map((m, i) => ({
    id: `${sid}-${i}`,
    role: m.role,
    content: m.content,
  }));
  const allMessages = [...serverMessages, ...pendingMessages];

  const handleSend = useCallback(async () => {
    if (!input.trim() || sendMessage.isPending || !pid) return;
    const text = input.trim();
    setInput('');

    const userMsg: LocalMessage = { role: 'user', content: text, id: Date.now().toString() };
    setPendingMessages((prev) => [...prev, userMsg]);

    try {
      const response = await sendMessage.mutateAsync(text);
      const msgContent =
        typeof response.message === 'string'
          ? response.message
          : (response.message as unknown as { content: string }).content;
      const aiMsg: LocalMessage = {
        role: 'assistant',
        content: msgContent,
        id: (Date.now() + 1).toString(),
      };
      setPendingMessages((prev) => [...prev, aiMsg]);
      setDisclaimer(response.disclaimer);
    } catch {
      setPendingMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Something went wrong. Please try again.', id: (Date.now() + 1).toString() },
      ]);
    }

    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
  }, [input, sendMessage, pid]);

  if (isLoading) return <LoadingSpinner />;

  if (error && allMessages.length === 0) {
    return (
      <View style={{ flex: 1, backgroundColor: Colors.background, alignItems: 'center', justifyContent: 'center', padding: Spacing.xl }}>
        <Icon name="stethoscope" size={32} color={Colors.textMuted} />
        <Text style={{ fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.md }}>
          Couldn't load session
        </Text>
        <Text style={{ fontSize: FontSize.sm, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.xs }}>
          Check your connection and try again
        </Text>
        <Pressable
          onPress={() => refetch()}
          style={({ pressed }) => ({
            marginTop: Spacing.lg,
            backgroundColor: Colors.primary,
            borderRadius: BorderRadius.md,
            borderCurve: 'continuous',
            paddingHorizontal: Spacing.lg,
            paddingVertical: Spacing.sm,
            opacity: pressed ? 0.85 : 1,
          })}
        >
          <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.textInverse }}>
            Retry
          </Text>
        </Pressable>
      </View>
    );
  }

  const phase = session?.diagnosis_state?.phase;
  const phaseInfo = phase ? PHASE_LABELS[phase] : undefined;

  return (
    <NoProfileGuard>
      <Stack.Screen
        options={{
          title: session?.chief_complaint || 'AI Diagnosis',
          headerRight: phaseInfo
            ? () => (
                <View
                  style={{
                    backgroundColor: phaseInfo.color + '18',
                    paddingHorizontal: Spacing.sm,
                    paddingVertical: Spacing.xs,
                    borderRadius: BorderRadius.full,
                    borderCurve: 'continuous',
                    marginRight: Spacing.sm,
                  }}
                >
                  <Text
                    style={{
                      fontSize: FontSize.xs,
                      fontWeight: FontWeight.semibold,
                      color: phaseInfo.color,
                    }}
                  >
                    {phaseInfo.label}
                  </Text>
                </View>
              )
            : undefined,
        }}
      />
      <KeyboardAvoidingView
        style={{ flex: 1, backgroundColor: Colors.background }}
        behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        <FlatList
          ref={flatListRef}
          data={allMessages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{
            padding: Spacing.md,
            gap: Spacing.sm,
            flexGrow: 1,
            justifyContent: allMessages.length === 0 ? 'center' : 'flex-start',
          }}
          contentInsetAdjustmentBehavior="automatic"
          renderItem={({ item }) => (
            <ChatBubble
              content={item.content}
              isUser={item.role === 'user'}
              animate={pendingMessages.some((m) => m.id === item.id)}
            />
          )}
          ListEmptyComponent={
            <View style={{ alignItems: 'center', padding: Spacing.xl }}>
              <Text style={{ fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center' }}>
                No messages yet
              </Text>
            </View>
          }
          ListFooterComponent={
            allMessages.length > 0 ? (
              <>
                {sendMessage.isPending && <TypingIndicator />}
                {disclaimer && (
                  <Animated.Text
                    entering={FadeIn.duration(300)}
                    style={{ fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md }}
                  >
                    {disclaimer}
                  </Animated.Text>
                )}
              </>
            ) : null
          }
          onLayout={() => {
            if (allMessages.length > 0) flatListRef.current?.scrollToEnd({ animated: false });
          }}
        />

        <ChatInput
          value={input}
          onChangeText={setInput}
          onSend={handleSend}
          isBusy={sendMessage.isPending}
          placeholder="Describe your symptoms…"
        />
      </KeyboardAvoidingView>
    </NoProfileGuard>
  );
}
