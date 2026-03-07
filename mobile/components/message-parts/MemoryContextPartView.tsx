import { useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { Icon } from '@/components/Icon';
import type { MessagePart } from '@/types/api';

type MemoryContextPart = Extract<MessagePart, { type: 'memory_context' }>;

export function MemoryContextPartView({ part }: { part: MemoryContextPart }) {
  const Colors = useColors();
  const [expanded, setExpanded] = useState(false);

  if (part.count === 0 && part.memories.length === 0) return null;

  return (
    <View style={{ marginBottom: Spacing.xs }}>
      <Pressable
        onPress={() => setExpanded((p) => !p)}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.xs,
          paddingVertical: Spacing.xs,
        }}
      >
        <Icon name="brain" size={14} color={Colors.textMuted} />
        <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: FontWeight.medium }}>
          {part.count} {part.count === 1 ? 'memory' : 'memories'} used
        </Text>
        <Icon
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={12}
          color={Colors.textMuted}
        />
      </Pressable>
      {expanded && (
        <View
          style={{
            backgroundColor: Colors.surfaceSecondary,
            borderRadius: BorderRadius.sm,
            borderCurve: 'continuous',
            padding: Spacing.sm,
            gap: 4,
          }}
        >
          {part.memories.map((mem, i) => (
            <Text
              key={i}
              style={{ fontSize: FontSize.xs - 1, color: Colors.textSecondary, lineHeight: 16 }}
              numberOfLines={3}
            >
              {mem.date ? `[${mem.date}] ` : ''}{mem.text}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}
