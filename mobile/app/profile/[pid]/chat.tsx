import { useState, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  FlatList,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { useSendChatMessage } from '@/hooks/useChat';
import { Colors } from '@/constants/colors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatScreen() {
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);

  const sendMessage = useSendChatMessage(pid);

  const handleSend = async () => {
    if (!input.trim() || sendMessage.isPending) return;
    const text = input.trim();
    setInput('');

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const response = await sendMessage.mutateAsync({
        content: text,
        conversation_id: conversationId ?? undefined,
      });

      setConversationId(response.message.conversation_id);
      setDisclaimer(response.disclaimer);

      const aiMsg: Message = {
        id: response.message.id,
        role: 'assistant',
        content: response.message.content,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch {
      const errMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Something went wrong. Please try again.',
      };
      setMessages((prev) => [...prev, errMsg]);
    }

    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
  };

  return (
    <>
      <Stack.Screen options={{ title: 'Health Chat' }} />
      <KeyboardAvoidingView
        style={{ flex: 1, backgroundColor: Colors.background }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        {messages.length === 0 ? (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.xl }}>
            <Text style={{ fontSize: FontSize.xl, fontWeight: FontWeight.bold, color: Colors.text, textAlign: 'center' }}>
              Ask a health question
            </Text>
            <Text style={{ fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.sm }}>
              I can help you understand medications, conditions, test results, and general health topics.
            </Text>
          </View>
        ) : (
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={(m) => m.id}
            contentContainerStyle={{ padding: Spacing.md, gap: Spacing.sm }}
            renderItem={({ item }) => {
              const isUser = item.role === 'user';
              return (
                <View style={{ alignItems: isUser ? 'flex-end' : 'flex-start' }}>
                  <View
                    style={{
                      backgroundColor: isUser ? Colors.accent : Colors.surface,
                      borderRadius: BorderRadius.lg,
                      borderBottomRightRadius: isUser ? BorderRadius.sm : BorderRadius.lg,
                      borderBottomLeftRadius: isUser ? BorderRadius.lg : BorderRadius.sm,
                      padding: Spacing.md,
                      maxWidth: '80%',
                      borderWidth: isUser ? 0 : 1,
                      borderColor: Colors.border,
                    }}
                  >
                    <Text
                      style={{
                        fontSize: FontSize.md,
                        color: isUser ? Colors.textInverse : Colors.text,
                        lineHeight: 22,
                      }}
                      selectable
                    >
                      {item.content}
                    </Text>
                  </View>
                </View>
              );
            }}
            ListFooterComponent={
              disclaimer ? (
                <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md }}>
                  {disclaimer}
                </Text>
              ) : null
            }
          />
        )}

        {/* Input */}
        <View
          style={{
            flexDirection: 'row',
            padding: Spacing.md,
            gap: Spacing.sm,
            backgroundColor: Colors.surface,
            borderTopWidth: 1,
            borderTopColor: Colors.border,
          }}
        >
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Ask a health question…"
            placeholderTextColor={Colors.textMuted}
            multiline
            style={{
              flex: 1,
              backgroundColor: Colors.background,
              borderWidth: 1,
              borderColor: Colors.border,
              borderRadius: BorderRadius.lg,
              padding: Spacing.sm,
              fontSize: FontSize.md,
              color: Colors.text,
              maxHeight: 100,
            }}
          />
          <Pressable
            onPress={handleSend}
            disabled={sendMessage.isPending || !input.trim()}
            style={({ pressed }) => ({
              backgroundColor:
                sendMessage.isPending || !input.trim() ? Colors.primaryLight : Colors.accent,
              borderRadius: BorderRadius.full,
              width: 44,
              height: 44,
              alignItems: 'center',
              justifyContent: 'center',
              alignSelf: 'flex-end',
              opacity: pressed ? 0.85 : 1,
            })}
          >
            <Text style={{ color: Colors.textInverse, fontSize: 18 }}>↑</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </>
  );
}
