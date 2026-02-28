import { Pressable, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { FontSize, FontWeight, Spacing, BorderRadius } from '@/constants/theme';

export type ConversationMode = 'chat' | 'diagnosis';

interface Props {
  mode: ConversationMode;
  onToggle: () => void;
}

export function ModeToggle({ mode, onToggle }: Props) {
  const Colors = useColors();
  const isChat = mode === 'chat';

  return (
    <Pressable
      onPress={() => {
        if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onToggle();
      }}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: Spacing.xs,
        paddingHorizontal: Spacing.sm,
        paddingVertical: Spacing.xs,
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous',
        backgroundColor: isChat ? Colors.primary + '12' : Colors.accent + '12',
        opacity: pressed ? 0.6 : 1,
        marginRight: Spacing.md,
      })}
    >
      <Icon
        name={isChat ? 'chat-fill' : 'stethoscope'}
        size={14}
        color={isChat ? Colors.primary : Colors.accent}
      />
      <Text
        style={{
          fontSize: FontSize.sm,
          fontWeight: FontWeight.semibold,
          color: isChat ? Colors.primary : Colors.accent,
        }}
      >
        {isChat ? 'Chat' : 'Diagnosis'}
      </Text>
    </Pressable>
  );
}
