import { View, Text } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight } from '@/constants/theme';

interface Props {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, subtitle, action }: Props) {
  const Colors = useColors();
  return (
    <View
      style={{
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: Spacing.xxl,
        gap: Spacing.sm,
      }}
    >
      <Text style={{ fontSize: FontSize.xl, color: Colors.textMuted }}>○</Text>
      <Text
        style={{
          fontSize: FontSize.md,
          color: Colors.text,
          fontWeight: FontWeight.semibold,
          textAlign: 'center',
        }}
      >
        {title}
      </Text>
      {subtitle && (
        <Text
          style={{
            fontSize: FontSize.sm,
            color: Colors.textSecondary,
            textAlign: 'center',
            maxWidth: 260,
          }}
        >
          {subtitle}
        </Text>
      )}
      {action}
    </View>
  );
}
