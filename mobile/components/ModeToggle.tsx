import { View, Text, Pressable } from 'react-native';
import { Icon } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { useHapticPress } from '@/hooks/useHapticPress';
import { useHeaderScale } from '@/hooks/useHeaderScale';
import { FontSize, FontWeight, Spacing, BorderRadius } from '@/constants/theme';

export type ConversationMode = 'chat' | 'diagnosis';

interface Props {
  mode: ConversationMode;
  onToggle: () => void;
}

export function ModeToggle({ mode, onToggle }: Props) {
  const Colors = useColors();
  const header = useHeaderScale();
  const handlePress = useHapticPress(onToggle);
  const isChat = mode === 'chat';
  const tint = isChat ? Colors.primary : Colors.accent;

  return (
    <Pressable
      onPress={handlePress}
      style={({ pressed }) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: Spacing.xs,
        paddingVertical: Spacing.xs - 2,
        paddingHorizontal: Spacing.sm,
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous',
        backgroundColor: tint + '15',
        opacity: pressed ? 0.6 : 1,
      })}
    >
      <Icon
        name={isChat ? 'chat-fill' : 'stethoscope'}
        size={header.iconSize - 2}
        color={tint}
      />
      <Text
        style={{
          fontSize: FontSize.xs,
          fontWeight: FontWeight.semibold,
          color: tint,
        }}
      >
        {isChat ? 'Chat' : 'Diagnosis'}
      </Text>
    </Pressable>
  );
}
