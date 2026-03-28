import { View, Text, ActivityIndicator } from 'react-native';
import Animated from 'react-native-reanimated';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight } from '@/constants/theme';
import { enterSlideUp } from '@/constants/animations';
import type { AgentStep } from '@/types/api';

interface Props {
  steps: AgentStep[];
}

export function AgentSteps({ steps }: Props) {
  const Colors = useColors();

  if (steps.length === 0) return null;

  return (
    <Animated.View
      entering={enterSlideUp()}
      style={{ gap: Spacing.xs, marginBottom: Spacing.sm }}
    >
      {steps.map((step, i) => (
        <View key={`${step.id}-${i}`}>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: Spacing.sm,
              paddingVertical: 2,
            }}
          >
            {step.status === 'active' ? (
              <ActivityIndicator size="small" color={Colors.primary} style={{ width: 16, height: 16 }} />
            ) : (
              <Text style={{ fontSize: 12, color: Colors.success, width: 16, textAlign: 'center' }}>
                ✓
              </Text>
            )}
            <Text
              style={{
                fontSize: FontSize.xs,
                color: step.status === 'active' ? Colors.text : Colors.textMuted,
                fontWeight: step.status === 'active' ? FontWeight.medium : FontWeight.regular,
                flex: 1,
              }}
              numberOfLines={1}
            >
              {step.message}
            </Text>
          </View>

          {/* Memory / detail sub-items */}
          {step.details && step.details.length > 0 && (
            <View style={{ marginLeft: 28, gap: 2, marginTop: 2 }}>
              {step.details.map((detail, j) => (
                <Text
                  key={j}
                  style={{
                    fontSize: FontSize.xs - 1,
                    color: Colors.textMuted,
                    lineHeight: 16,
                  }}
                  numberOfLines={2}
                >
                  {detail}
                </Text>
              ))}
            </View>
          )}
        </View>
      ))}
    </Animated.View>
  );
}
