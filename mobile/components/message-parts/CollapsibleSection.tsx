import { useState, type ReactNode } from 'react';
import { View, Text, Pressable } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { Icon, type IconName } from '@/components/Icon';

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
        <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={12} color={Colors.textMuted} />
      </Pressable>
      {expanded && (
        <View style={{ padding: Spacing.sm, backgroundColor: Colors.surfaceSecondary }}>
          {children}
        </View>
      )}
    </View>
  );
}
