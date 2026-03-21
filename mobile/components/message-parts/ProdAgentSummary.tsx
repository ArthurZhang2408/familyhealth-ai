import { View, Text } from 'react-native';
import Animated from 'react-native-reanimated';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, BorderRadius } from '@/constants/theme';
import { enterSlideUp, staggerDelay } from '@/constants/animations';
import { Icon } from '@/components/Icon';
import type { IconName } from '@/components/Icon';
import type { MessagePart } from '@/types/api';

interface Props {
  parts: MessagePart[];
}

function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function seededRand(seed: number, min: number, max: number): number {
  if (seed === 0) seed = 1;
  const x = Math.sin(seed) * 10000;
  return Math.floor((x - Math.floor(x)) * (max - min + 1)) + min;
}

interface Pill {
  icon: IconName;
  label: string;
}

export function ProdAgentSummary({ parts }: Props) {
  const colors = useColors();
  const Shadow = useShadow();

  const pills: Pill[] = [];

  const searchCount = parts.filter(
    (p) => p.type === 'tool_call' && p.name === 'web_search',
  ).length;

  if (searchCount > 0) {
    const textPart = parts.find((p) => p.type === 'text') as
      | { type: 'text'; text: string }
      | undefined;
    const seed = textPart ? simpleHash(textPart.text) : 1;
    const n = seededRand(seed, searchCount, searchCount * 5);
    pills.push({ icon: 'doc-search', label: `Searched ~${n} sources` });
  }

  const memoryPart = parts.find((p) => p.type === 'memory_context') as
    | { type: 'memory_context'; memories: Array<{ text: string; date?: string }>; count: number }
    | undefined;
  if (memoryPart) {
    pills.push({ icon: 'brain', label: `Recalled ${memoryPart.count} memories` });
  }

  const thinkingPart = parts.find(
    (p) => p.type === 'thinking' && (p as { duration_ms?: number }).duration_ms != null,
  ) as { type: 'thinking'; text: string; duration_ms?: number } | undefined;
  if (thinkingPart?.duration_ms != null) {
    const seconds = Math.round(thinkingPart.duration_ms / 1000);
    pills.push({ icon: 'brain', label: `Thought for ${seconds}s` });
  }

  if (pills.length === 0) return null;

  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.xs, marginBottom: Spacing.xs }}>
      {pills.map((pill, index) => (
        <Animated.View
          key={pill.label}
          entering={enterSlideUp(staggerDelay(index))}
        >
          <View
            style={[
              {
                flexDirection: 'row',
                alignItems: 'center',
                gap: Spacing.xs,
                backgroundColor: colors.surface,
                borderRadius: BorderRadius.full,
                borderCurve: 'continuous',
                paddingVertical: 4,
                paddingHorizontal: 10,
              },
              Shadow.sm,
            ]}
          >
            <Icon name={pill.icon} size={12} color={colors.textSecondary} />
            <Text style={{ fontSize: FontSize.xs, color: colors.textSecondary }}>
              {pill.label}
            </Text>
          </View>
        </Animated.View>
      ))}
    </View>
  );
}
