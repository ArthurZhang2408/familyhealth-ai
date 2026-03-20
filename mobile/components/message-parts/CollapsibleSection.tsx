import { useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import Animated, {
  FadeIn,
  FadeOut,
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from 'react-native-reanimated';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { Icon, type IconName } from '@/components/Icon';
import { Springs } from '@/constants/animations';
import type { ReactNode } from 'react';

export function CollapsibleSection({
  icon,
  label,
  defaultExpanded = false,
  children,
}: {
  icon: IconName;
  label: string;
  defaultExpanded?: boolean;
  children: ReactNode;
}) {
  const Colors = useColors();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const rotation = useSharedValue(defaultExpanded ? 180 : 0);

  const chevronStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }));

  const toggle = () => {
    const next = !expanded;
    setExpanded(next);
    rotation.value = withSpring(next ? 180 : 0, Springs.snappy);
  };

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
        onPress={toggle}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.xs,
          padding: Spacing.sm,
          backgroundColor: Colors.surface,
        }}
      >
        <Icon name={icon} size={14} color={Colors.textMuted} />
        <Text
          style={{
            fontSize: FontSize.xs,
            color: Colors.textSecondary,
            fontWeight: FontWeight.medium,
            flex: 1,
          }}
          numberOfLines={1}
        >
          {label}
        </Text>
        <Animated.View style={chevronStyle}>
          <Icon name="chevron-down" size={12} color={Colors.textMuted} />
        </Animated.View>
      </Pressable>
      {expanded && (
        <Animated.View
          entering={FadeIn.duration(200)}
          exiting={FadeOut.duration(150)}
          style={{ padding: Spacing.sm, backgroundColor: Colors.surfaceSecondary }}
        >
          {children}
        </Animated.View>
      )}
    </View>
  );
}
