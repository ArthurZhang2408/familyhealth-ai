import { Text } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { FontSize } from '@/constants/theme';
import { CollapsibleSection } from './CollapsibleSection';
import type { MessagePart } from '@/types/api';

type ThinkingPart = Extract<MessagePart, { type: 'thinking' }>;

export function ThinkingPartView({
  part,
  defaultExpanded = false,
}: {
  part: ThinkingPart;
  defaultExpanded?: boolean;
}) {
  const Colors = useColors();

  return (
    <CollapsibleSection icon="brain" label="Reasoning" defaultExpanded={defaultExpanded}>
      <Text
        style={{
          fontSize: FontSize.xs,
          color: Colors.textMuted,
          fontStyle: 'italic',
          lineHeight: 18,
        }}
        selectable
      >
        {part.text}
      </Text>
    </CollapsibleSection>
  );
}
