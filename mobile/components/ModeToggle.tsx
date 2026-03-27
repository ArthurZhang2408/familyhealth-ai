import { HeaderIconButton } from '@/components/HeaderIconButton';
import { useColors } from '@/hooks/useColors';

export type ConversationMode = 'chat' | 'diagnosis';

interface Props {
  mode: ConversationMode;
  onToggle: () => void;
}

export function ModeToggle({ mode, onToggle }: Props) {
  const Colors = useColors();
  const isChat = mode === 'chat';

  return (
    <HeaderIconButton
      icon={isChat ? 'chat-fill' : 'stethoscope'}
      onPress={onToggle}
      tint={isChat ? Colors.primary : Colors.accent}
    />
  );
}
