import { useState, useRef, useCallback } from 'react';
import { View, Text, Pressable, FlatList, KeyboardAvoidingView } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { ChatBubble, TypingIndicator } from '@/components/ChatBubble';
import { ChatInput } from '@/components/ChatInput';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Icon } from '@/components/Icon';
import Animated, { FadeIn } from 'react-native-reanimated';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { useProfileStore } from '@/stores/profile';
import { useChatConversation, useSendChatMessage } from '@/hooks/useChat';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatScreen() {
  const Colors = useColors();
  const { cid } = useLocalSearchParams<{ cid: string }>();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';

  // Local messages sent during this session (appended on top of server data)
  const [pendingMessages, setPendingMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState('');
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);

  const { data: conversation, isLoading, error, refetch } = useChatConversation(pid, cid);
  const sendMessage = useSendChatMessage(pid);

  // Merge server messages + locally sent messages
  const serverMessages: LocalMessage[] = (conversation?.messages ?? []).map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
  }));
  const allMessages = [...serverMessages, ...pendingMessages];

  const handleSend = useCallback(async () => {
    if (!input.trim() || sendMessage.isPending || !pid) return;
    const text = input.trim();
    setInput('');

    const userMsg: LocalMessage = { id: Date.now().toString(), role: 'user', content: text };
    setPendingMessages((prev) => [...prev, userMsg]);

    try {
      const response = await sendMessage.mutateAsync({
        content: text,
        conversation_id: cid,
      });

      setDisclaimer(response.disclaimer);

      const aiMsg: LocalMessage = {
        id: response.message.id,
        role: 'assistant',
        content: response.message.content,
      };
      setPendingMessages((prev) => [...prev, aiMsg]);
    } catch {
      setPendingMessages((prev) => [
        ...prev,
        { id: (Date.now() + 1).toString(), role: 'assistant', content: 'Something went wrong. Please try again.' },
      ]);
    }

    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
  }, [input, sendMessage, pid, cid]);

  // Single loading state — skeleton until data or error arrives
  if (isLoading) return <LoadingSpinner />;

  // Error state with retry
  if (error && allMessages.length === 0) {
    return (
      <View style={{ flex: 1, backgroundColor: Colors.background, alignItems: 'center', justifyContent: 'center', padding: Spacing.xl }}>
        <Icon name="chat-bubbles" size={32} color={Colors.textMuted} />
        <Text style={{ fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.md }}>
          Couldn't load conversation
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

  return (
    <NoProfileGuard>
      <Stack.Screen options={{ title: conversation?.topic || 'Health Chat' }} />
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
          onLayout={() => flatListRef.current?.scrollToEnd({ animated: false })}
        />

        <ChatInput
          value={input}
          onChangeText={setInput}
          onSend={handleSend}
          isBusy={sendMessage.isPending}
          placeholder="Ask a health question…"
        />
      </KeyboardAvoidingView>
    </NoProfileGuard>
  );
}
