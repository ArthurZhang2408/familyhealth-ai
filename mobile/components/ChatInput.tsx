import { View, TextInput, Pressable, ActivityIndicator } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, BorderRadius } from '@/constants/theme';

interface Props {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  isBusy: boolean;
  placeholder?: string;
  onAttach?: () => void;
}

export function ChatInput({
  value,
  onChangeText,
  onSend,
  isBusy,
  placeholder = 'Type a message…',
  onAttach,
}: Props) {
  const Colors = useColors();
  const Shadow = useShadow();
  const canSend = value.trim().length > 0 && !isBusy;

  return (
    <View
      style={{
        paddingHorizontal: Spacing.md,
        paddingTop: Spacing.sm,
        paddingBottom: Spacing.md,
        backgroundColor: Colors.background,
      }}
    >
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'flex-end',
          gap: Spacing.sm,
          backgroundColor: Colors.surface,
          borderRadius: BorderRadius.xl,
          borderCurve: 'continuous',
          paddingHorizontal: Spacing.xs,
          paddingVertical: Spacing.xs,
          ...Shadow.md,
        }}
      >
        {/* Attach button */}
        {onAttach && (
          <Pressable
            onPress={() => {
              if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              onAttach();
            }}
            style={({ pressed }) => ({
              width: 36,
              height: 36,
              borderRadius: BorderRadius.full,
              backgroundColor: Colors.surfaceSecondary,
              alignItems: 'center',
              justifyContent: 'center',
              borderCurve: 'continuous',
              opacity: pressed ? 0.6 : 1,
              alignSelf: 'flex-end',
            })}
          >
            <Icon name="plus" size={20} color={Colors.textSecondary} />
          </Pressable>
        )}

        {/* Text input */}
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={Colors.textMuted}
          multiline
          style={{
            flex: 1,
            fontSize: FontSize.md,
            color: Colors.text,
            maxHeight: 120,
            minHeight: 36,
            paddingHorizontal: Spacing.sm,
            paddingVertical: Spacing.sm,
          }}
        />

        {/* Send button */}
        <Pressable
          onPress={() => {
            if (canSend) {
              if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
              onSend();
            }
          }}
          disabled={!canSend}
          style={({ pressed }) => ({
            width: 36,
            height: 36,
            borderRadius: BorderRadius.full,
            backgroundColor: canSend ? Colors.primary : Colors.primaryLight,
            alignItems: 'center',
            justifyContent: 'center',
            borderCurve: 'continuous',
            opacity: pressed ? 0.85 : 1,
            alignSelf: 'flex-end',
          })}
        >
          {isBusy ? (
            <ActivityIndicator size="small" color={Colors.textInverse} />
          ) : (
            <Icon name="arrow-up" size={18} color={Colors.textInverse} />
          )}
        </Pressable>
      </View>
    </View>
  );
}
