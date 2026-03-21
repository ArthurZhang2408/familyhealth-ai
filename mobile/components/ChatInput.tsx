import { useRef } from 'react';
import { View, Text, TextInput, Pressable, ActivityIndicator, Image } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withSequence,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/Icon';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { enterSlideUp, exitFade, Springs } from '@/constants/animations';
import type { Attachment } from '@/hooks/useAttachMenu';

interface Props {
  value: string;
  onChangeText: (text: string) => void;
  onSend: () => void;
  isBusy: boolean;
  placeholder?: string;
  onAttach?: () => void;
  attachment?: Attachment | null;
  onRemoveAttachment?: () => void;
}

const THUMB = 64;

export function ChatInput({
  value,
  onChangeText,
  onSend,
  isBusy,
  placeholder = 'Type a message…',
  onAttach,
  attachment,
  onRemoveAttachment,
}: Props) {
  const Colors = useColors();
  const inputRef = useRef<TextInput>(null);
  const hasAttachment = !!attachment;
  const canSend = (value.trim().length > 0 || hasAttachment) && !isBusy;

  // Send button scale spring
  const sendScale = useSharedValue(1);
  const sendScaleStyle = useAnimatedStyle(() => ({
    transform: [{ scale: sendScale.value }],
  }));

  // Flag: send is pending, waiting for auto-correct to commit via onEndEditing
  const pendingSendRef = useRef(false);

  const handleSendPress = () => {
    if (!canSend) return;
    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    sendScale.value = withSequence(
      withSpring(0.9, Springs.snappy),
      withSpring(1, Springs.snappy),
    );
    // Blur to accept pending iOS auto-correct. The actual send happens in
    // onEndEditing after iOS commits the corrected text.
    // If input is already blurred (keyboard dismissed), send directly —
    // .blur() is a no-op on unfocused input and onEndEditing won't fire.
    if (!inputRef.current?.isFocused()) {
      onSend();
      return;
    }
    pendingSendRef.current = true;
    inputRef.current.blur();
  };

  const handleEndEditing = (e: { nativeEvent: { text: string } }) => {
    if (!pendingSendRef.current) return;
    pendingSendRef.current = false;
    // Push the final (auto-corrected) text to parent state, then send next tick
    onChangeText(e.nativeEvent.text);
    setTimeout(() => onSend(), 0);
  };

  return (
    <View
      style={{
        paddingHorizontal: Spacing.md,
        paddingTop: Spacing.sm,
        paddingBottom: Spacing.xl,
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
        {/* Attachment thumbnail preview */}
        {attachment && attachment.type.startsWith('image/') && (
          <Animated.View entering={enterSlideUp()} exiting={exitFade()} style={{ paddingHorizontal: Spacing.md, paddingTop: Spacing.sm }}>
            <View style={{ alignSelf: 'flex-start', position: 'relative' }}>
              <Image
                source={{ uri: attachment.uri }}
                style={{
                  width: THUMB,
                  height: THUMB,
                  borderRadius: BorderRadius.md,
                  backgroundColor: Colors.surfaceSecondary,
                }}
                resizeMode="cover"
              />
              {onRemoveAttachment && (
                <Pressable
                  onPress={() => {
                    if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    onRemoveAttachment();
                  }}
                  style={{
                    position: 'absolute',
                    top: -6,
                    right: -6,
                    width: 20,
                    height: 20,
                    borderRadius: 10,
                    backgroundColor: Colors.textSecondary,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Icon name="close" size={12} color={Colors.background} />
                </Pressable>
              )}
            </View>
          </Animated.View>
        )}

        {/* PDF attachment indicator */}
        {attachment && !attachment.type.startsWith('image/') && (
          <Animated.View
            entering={enterSlideUp()}
            exiting={exitFade()}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: Spacing.xs,
              paddingHorizontal: Spacing.md,
              paddingTop: Spacing.sm,
            }}
          >
            <Icon name="document" size={14} color={Colors.primary} />
            <Text
              style={{ fontSize: FontSize.xs, color: Colors.primary, fontWeight: FontWeight.medium, flex: 1 }}
              numberOfLines={1}
            >
              {attachment.name}
            </Text>
            {onRemoveAttachment && (
              <Pressable onPress={onRemoveAttachment}>
                <Icon name="close" size={14} color={Colors.textMuted} />
              </Pressable>
            )}
          </Animated.View>
        )}

        {/* Text input area */}
        <TextInput
          ref={inputRef}
          value={value}
          onChangeText={onChangeText}
          onEndEditing={handleEndEditing}
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

          {/* Send button with scale spring */}
          <Animated.View style={sendScaleStyle}>
            <Pressable
              onPress={handleSendPress}
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
          </Animated.View>
        </View>
      </View>
    </View>
  );
}
