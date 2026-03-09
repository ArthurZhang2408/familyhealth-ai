import { useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { Icon } from '@/components/Icon';
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
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: Colors.border,
        borderRadius: BorderRadius.sm,
        borderCurve: 'continuous',
        marginBottom: Spacing.xs,
        overflow: 'hidden',
      }}
    >
      <Pressable
        onPress={() => setExpanded((p) => !p)}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.xs,
          padding: Spacing.sm,
          backgroundColor: Colors.surface,
        }}
      >
        <Text style={{ fontSize: 12, width: 16, textAlign: 'center' }}>🧠</Text>
        <Text
          style={{
            fontSize: FontSize.xs,
            color: Colors.textSecondary,
            fontWeight: FontWeight.medium,
            flex: 1,
          }}
          numberOfLines={1}
        >
          Reasoning
        </Text>
        <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={12} color={Colors.textMuted} />
      </Pressable>
      {expanded && (
        <View
          style={{
            padding: Spacing.sm,
            backgroundColor: Colors.surfaceSecondary,
          }}
        >
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
        </View>
      )}
    </View>
  );
}
