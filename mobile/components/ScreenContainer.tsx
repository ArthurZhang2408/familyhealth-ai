import { ScrollView, View, type ViewStyle } from 'react-native';
import { Colors } from '@/constants/colors';
import { Spacing } from '@/constants/theme';

interface Props {
  children: React.ReactNode;
  scrollable?: boolean;
  style?: ViewStyle;
  contentStyle?: ViewStyle;
}

export function ScreenContainer({ children, scrollable = true, style, contentStyle }: Props) {
  if (!scrollable) {
    return (
      <View style={[{ flex: 1, backgroundColor: Colors.background }, style]}>
        {children}
      </View>
    );
  }

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      style={{ flex: 1, backgroundColor: Colors.background, ...style }}
      contentContainerStyle={{
        padding: Spacing.md,
        gap: Spacing.md,
        ...contentStyle,
      }}
    >
      {children}
    </ScrollView>
  );
}
