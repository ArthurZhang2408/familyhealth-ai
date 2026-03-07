import { View, Text } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize } from '@/constants/theme';
import type { MessagePart } from '@/types/api';

type AgentStepsPart = Extract<MessagePart, { type: 'agent_steps' }>;

export function AgentStepsPartView({ part }: { part: AgentStepsPart }) {
  const Colors = useColors();

  return (
    <View style={{ gap: Spacing.xs, marginBottom: Spacing.xs }}>
      {part.steps.map((step, i) => (
        <View key={`${step.id}-${i}`}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, paddingVertical: 2 }}>
            <Text style={{ fontSize: 12, color: Colors.success, width: 16, textAlign: 'center' }}>
              ✓
            </Text>
            <Text
              style={{ fontSize: FontSize.xs, color: Colors.textMuted, flex: 1 }}
              numberOfLines={1}
            >
              {step.message}
            </Text>
          </View>
          {step.details && step.details.length > 0 && (
            <View style={{ marginLeft: 28, gap: 2, marginTop: 2 }}>
              {step.details.map((detail, j) => (
                <Text
                  key={j}
                  style={{ fontSize: FontSize.xs - 1, color: Colors.textMuted, lineHeight: 16 }}
                  numberOfLines={2}
                >
                  {detail}
                </Text>
              ))}
            </View>
          )}
        </View>
      ))}
    </View>
  );
}
