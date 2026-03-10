import { Text } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { FontSize } from '@/constants/theme';
import { CollapsibleSection } from './CollapsibleSection';
import type { MessagePart } from '@/types/api';

type MemoryContextPart = Extract<MessagePart, { type: 'memory_context' }>;

export function MemoryContextPartView({ part }: { part: MemoryContextPart }) {
  const Colors = useColors();

  if (part.count === 0 && part.memories.length === 0) return null;

  return (
    <CollapsibleSection
      icon="brain"
      label={`${part.count} ${part.count === 1 ? 'memory' : 'memories'} used`}
    >
      {part.memories.map((mem, i) => (
        <Text
          key={i}
          style={{ fontSize: FontSize.xs - 1, color: Colors.textSecondary, lineHeight: 16 }}
          selectable
        >
          {mem.date ? `[${mem.date}] ` : ''}
          {mem.text}
        </Text>
      ))}
    </CollapsibleSection>
  );
}
