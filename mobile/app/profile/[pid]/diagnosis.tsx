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
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useCreateDiagnosisSession, useSendDiagnosisMessage } from '@/hooks/useDiagnosis';
import { Colors } from '@/constants/colors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  id: string;
}

export default function DiagnosisScreen() {
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);

  const createSession = useCreateDiagnosisSession(pid);
  const sendMessage = useSendDiagnosisMessage(pid, sessionId ?? '');

  const isBusy = createSession.isPending || sendMessage.isPending;

  const handleSend = async () => {
    if (!input.trim() || isBusy) return;
    const text = input.trim();
    setInput('');

    const userMsg: Message = { role: 'user', content: text, id: Date.now().toString() };
    setMessages((prev) => [...prev, userMsg]);

    try {
      if (!sessionId) {
        // First message — create a session
        const session = await createSession.mutateAsync(text);
        setSessionId(session.id);
        // The first AI response comes back via sendMessage after session is created
        // For the scaffold, show a placeholder response
        const aiMsg: Message = {
          role: 'assistant',
          content: 'Thank you for describing your symptoms. Could you tell me more about when this started?',
          id: (Date.now() + 1).toString(),
        };
        setMessages((prev) => [...prev, aiMsg]);
      } else {
        const response = await sendMessage.mutateAsync(text);
        const aiMsg: Message = {
          role: 'assistant',
          content: response.message,
          id: (Date.now() + 1).toString(),
        };
        setMessages((prev) => [...prev, aiMsg]);
        setDisclaimer(response.disclaimer);
      }
    } catch {
      const errMsg: Message = {
        role: 'assistant',
        content: 'Something went wrong. Please try again.',
        id: (Date.now() + 1).toString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    }

    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
  };

  return (
    <>
      <Stack.Screen options={{ title: 'AI Diagnosis' }} />
      <KeyboardAvoidingView
        style={{ flex: 1, backgroundColor: Colors.background }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        {messages.length === 0 ? (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.xl }}>
            <Text style={{ fontSize: FontSize.xl, fontWeight: FontWeight.bold, color: Colors.text, textAlign: 'center' }}>
              Describe your symptoms
            </Text>
            <Text style={{ fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.sm }}>
              Type your chief complaint and the AI will guide you through a structured assessment.
            </Text>
          </View>
        ) : (
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={(m) => m.id}
            contentContainerStyle={{ padding: Spacing.md, gap: Spacing.sm }}
            renderItem={({ item }) => <ChatBubble message={item} />}
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
            placeholder="Describe your symptoms…"
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
            disabled={isBusy || !input.trim()}
            style={({ pressed }) => ({
              backgroundColor: isBusy || !input.trim() ? Colors.primaryLight : Colors.primary,
              borderRadius: BorderRadius.full,
              width: 44,
              height: 44,
              alignItems: 'center',
              justifyContent: 'center',
              alignSelf: 'flex-end',
              opacity: pressed ? 0.85 : 1,
            })}
          >
            {isBusy ? (
              <Text style={{ color: Colors.textInverse }}>…</Text>
            ) : (
              <Text style={{ color: Colors.textInverse, fontSize: 18 }}>↑</Text>
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </>
  );
}

function ChatBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  return (
    <View style={{ alignItems: isUser ? 'flex-end' : 'flex-start' }}>
      <View
        style={{
          backgroundColor: isUser ? Colors.primary : Colors.surface,
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
          {message.content}
        </Text>
      </View>
    </View>
  );
}
