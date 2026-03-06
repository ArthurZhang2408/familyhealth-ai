import { useRef } from 'react';
import { View, Text, TextInput, Pressable, ActivityIndicator } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';

interface Props {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  isBusy: boolean;
  placeholder?: string;
  onAttach?: () => void;
  /** Show an attachment indicator badge on the + button */
  hasAttachment?: boolean;
}

export function ChatInput({
  value,
  onChangeText,
  onSend,
  isBusy,
  placeholder = 'Type a message…',
  onAttach,
  hasAttachment,
}: Props) {
  const Colors = useColors();
  const inputRef = useRef<TextInput>(null);
  const canSend = (value.trim().length > 0 || hasAttachment) && !isBusy;

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
          backgroundColor: Colors.surface,
          borderRadius: BorderRadius.xl,
          borderCurve: 'continuous',
          borderWidth: 1,
          borderColor: Colors.border,
        }}
      >
        {/* Attachment indicator */}
        {hasAttachment && (
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: Spacing.xs,
              paddingHorizontal: Spacing.md,
              paddingTop: Spacing.sm,
            }}
          >
            <Icon name="image" size={14} color={Colors.primary} />
            <Text style={{ fontSize: FontSize.xs, color: Colors.primary, fontWeight: FontWeight.medium }}>
              Image attached
            </Text>
          </View>
        )}

        {/* Text input area */}
        <TextInput
          ref={inputRef}
          value={value}
          onChangeText={onChangeText}
          placeholder={hasAttachment ? 'Add a message (optional)…' : placeholder}
          placeholderTextColor={Colors.textMuted}
          multiline
          style={{
            fontSize: FontSize.md,
            color: Colors.text,
            maxHeight: 120,
            minHeight: 44,
            paddingHorizontal: Spacing.md,
            paddingTop: hasAttachment ? Spacing.xs : Spacing.md,
            paddingBottom: Spacing.sm,
          }}
        />

        {/* Bottom toolbar */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingHorizontal: Spacing.sm,
            paddingBottom: Spacing.sm,
          }}
        >
          {/* Left actions */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.xs }}>
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
                  backgroundColor: hasAttachment ? Colors.primary + '20' : Colors.surfaceSecondary,
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderCurve: 'continuous',
                  opacity: pressed ? 0.6 : 1,
                })}
              >
                <Icon name="plus" size={20} color={hasAttachment ? Colors.primary : Colors.textSecondary} />
              </Pressable>
            )}
          </View>

          {/* Send button */}
          <Pressable
            onPress={() => {
              if (canSend) {
                if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                onSend();
                // Clear native state AFTER send reads the value.
                // clear() resets the native TextInput, preventing a pending
                // autocorrect suggestion from re-populating via onChangeText.
                inputRef.current?.clear();
                inputRef.current?.blur();
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
    </View>
  );
}
