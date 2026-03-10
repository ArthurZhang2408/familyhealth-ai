import { useState, useCallback } from 'react';
import { View, Text, Pressable } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { useHapticPress } from '@/hooks/useHapticPress';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { MessagePart } from '@/types/api';

type StructuredInputPart = Extract<MessagePart, { type: 'structured_input' }>;

interface Props {
  part: StructuredInputPart;
  onResponse?: (content: string, structuredResponse: Record<string, unknown>) => void;
  isLatest: boolean;
}

export function StructuredInputView({ part, onResponse, isLatest }: Props) {
  // Track local selection for instant rendering before server round-trip
  const [localSelected, setLocalSelected] = useState<unknown>(undefined);
  const effectiveSelected = localSelected !== undefined ? localSelected : part.selected;
  const isInteractive = effectiveSelected == null && isLatest && !!onResponse;

  const handleResponse = useCallback(
    (content: string, structuredResponse: Record<string, unknown>) => {
      setLocalSelected(structuredResponse.selected);
      onResponse?.(content, structuredResponse);
    },
    [onResponse],
  );

  switch (part.input_type) {
    case 'multiple_choice':
      return <MultipleChoice part={part} selected={effectiveSelected} onResponse={handleResponse} interactive={isInteractive} />;
    case 'scale':
      return <ScaleInput part={part} selected={effectiveSelected} onResponse={handleResponse} interactive={isInteractive} />;
    case 'yes_no':
      return <YesNo part={part} selected={effectiveSelected} onResponse={handleResponse} interactive={isInteractive} />;
    case 'multi_select':
      return <MultiSelect part={part} selected={effectiveSelected} onResponse={handleResponse} interactive={isInteractive} />;
    default:
      return null;
  }
}

function MultipleChoice({
  part,
  selected,
  onResponse,
  interactive,
}: {
  part: StructuredInputPart;
  selected: unknown;
  onResponse?: Props['onResponse'];
  interactive: boolean;
}) {
  const Colors = useColors();
  const options = (part.options ?? []) as Array<{ label: string; value: string }>;

  const handleSelect = useCallback(
    (opt: { label: string; value: string }) => {
      const isNone = opt.value.toLowerCase().includes('none') || opt.label.toLowerCase().includes('none of');
      const rejected = options.filter((o) => o.value !== opt.value).map((o) => o.label);
      // When "None" is selected, don't list rejected options — models
      // misinterpret alarming symptom names even when marked "Not selected"
      const content = isNone
        ? `Selected: ${opt.label}.`
        : `Selected: ${opt.label}. Not selected: ${rejected.join(', ')}.`;
      onResponse?.(content, {
        input_type: part.input_type,
        prompt: part.prompt,
        selected: opt.value,
      });
    },
    [onResponse, options, part.input_type, part.prompt],
  );

  return (
    <View style={{ gap: Spacing.sm, marginTop: Spacing.sm }}>
      <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.text }}>
        {part.prompt}
      </Text>
      {options.map((opt) => {
        const isSelected = selected === opt.value;
        return (
          <OptionCard
            key={opt.value}
            label={opt.label}
            selected={isSelected}
            disabled={!interactive}
            onPress={() => handleSelect(opt)}
          />
        );
      })}
    </View>
  );
}

function YesNo({
  part,
  selected,
  onResponse,
  interactive,
}: {
  part: StructuredInputPart;
  selected: unknown;
  onResponse?: Props['onResponse'];
  interactive: boolean;
}) {
  const Colors = useColors();

  const handleSelect = useCallback(
    (value: 'yes' | 'no') => {
      onResponse?.(`Selected: ${value === 'yes' ? 'Yes' : 'No'}`, {
        input_type: part.input_type,
        prompt: part.prompt,
        selected: value,
      });
    },
    [onResponse, part.input_type, part.prompt],
  );

  return (
    <View style={{ gap: Spacing.sm, marginTop: Spacing.sm }}>
      <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.text }}>
        {part.prompt}
      </Text>
      <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
        <OptionCard
          label="Yes"
          selected={selected === 'yes'}
          disabled={!interactive}
          onPress={() => handleSelect('yes')}
          flex
        />
        <OptionCard
          label="No"
          selected={selected === 'no'}
          disabled={!interactive}
          onPress={() => handleSelect('no')}
          flex
        />
      </View>
    </View>
  );
}

function ScaleInput({
  part,
  selected,
  onResponse,
  interactive,
}: {
  part: StructuredInputPart;
  selected: unknown;
  onResponse?: Props['onResponse'];
  interactive: boolean;
}) {
  const Colors = useColors();
  const range = (part.range ?? { min: 1, max: 10 }) as {
    min: number;
    max: number;
    step?: number;
    labels?: { min: string; max: string };
  };
  const [value, setValue] = useState<number | null>(null);
  const displayValue = selected != null ? Number(selected) : value;
  const step = range.step ?? 1;
  const steps: number[] = [];
  for (let i = range.min; i <= range.max; i += step) steps.push(i);

  const handleSelect = useCallback(
    (v: number) => {
      if (!interactive) return;
      setValue(v);
    },
    [interactive],
  );

  const handleSubmit = useHapticPress(
    useCallback(() => {
      if (value == null) return;
      onResponse?.(`Selected: ${value}/${range.max}`, {
        input_type: part.input_type,
        prompt: part.prompt,
        selected: value,
      });
    }, [onResponse, value, range.max, part.input_type, part.prompt]),
  );

  return (
    <View style={{ gap: Spacing.sm, marginTop: Spacing.sm }}>
      <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.text }}>
        {part.prompt}
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.xs }}>
        {steps.map((n) => {
          const isSelected = displayValue === n;
          return (
            <Pressable
              key={n}
              onPress={() => handleSelect(n)}
              disabled={!interactive}
              style={({ pressed }) => ({
                width: 36,
                height: 36,
                borderRadius: 18,
                borderWidth: 1.5,
                borderColor: isSelected ? Colors.primary : Colors.border,
                backgroundColor: isSelected ? Colors.primary : Colors.surface,
                alignItems: 'center',
                justifyContent: 'center',
                opacity: pressed ? 0.85 : !interactive && !isSelected ? 0.5 : 1,
              })}
            >
              <Text
                style={{
                  fontSize: FontSize.sm,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.regular,
                  color: isSelected ? Colors.textInverse : Colors.text,
                }}
              >
                {n}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>
          {range.labels?.min ?? `${range.min}`}
        </Text>
        <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>
          {range.labels?.max ?? `${range.max}`}
        </Text>
      </View>
      {interactive && value != null && (
        <SubmitButton label={`Submit: ${value}`} onPress={handleSubmit} />
      )}
    </View>
  );
}

function MultiSelect({
  part,
  selected: effectiveSelected,
  onResponse,
  interactive,
}: {
  part: StructuredInputPart;
  selected: unknown;
  onResponse?: Props['onResponse'];
  interactive: boolean;
}) {
  const Colors = useColors();
  const options = (part.options ?? []) as Array<{ label: string; value: string }>;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const completedSelection = effectiveSelected as string[] | null;

  const toggle = useCallback((value: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }, []);

  const handleSubmit = useHapticPress(
    useCallback(() => {
      const values = Array.from(selected);
      const selectedLabels = options.filter((o) => selected.has(o.value)).map((o) => o.label);
      const rejectedLabels = options
        .filter((o) => !selected.has(o.value))
        .map((o) => o.label)
        // Filter out "None of the above" from rejected list when user selected actual symptoms
        .filter((l) => !l.toLowerCase().includes('none of'));
      const parts: string[] = [];
      if (selectedLabels.length > 0) parts.push(`Has: ${selectedLabels.join(', ')}`);
      if (rejectedLabels.length > 0) parts.push(`Does NOT have: ${rejectedLabels.join(', ')}`);
      onResponse?.(parts.join('. ') + '.', {
        input_type: part.input_type,
        prompt: part.prompt,
        selected: values,
      });
    }, [onResponse, selected, options, part.input_type, part.prompt]),
  );

  return (
    <View style={{ gap: Spacing.sm, marginTop: Spacing.sm }}>
      <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.text }}>
        {part.prompt}
      </Text>
      {options.map((opt) => {
        const isChecked = interactive
          ? selected.has(opt.value)
          : Array.isArray(completedSelection) && completedSelection.includes(opt.value);
        return (
          <Pressable
            key={opt.value}
            onPress={interactive ? () => toggle(opt.value) : undefined}
            disabled={!interactive}
            style={({ pressed }) => ({
              flexDirection: 'row',
              alignItems: 'center',
              gap: Spacing.sm,
              paddingVertical: Spacing.sm,
              paddingHorizontal: Spacing.md,
              borderRadius: BorderRadius.md,
              borderCurve: 'continuous',
              borderWidth: 1,
              borderColor: isChecked ? Colors.primary : Colors.border,
              backgroundColor: isChecked ? Colors.primary + '10' : Colors.surface,
              opacity: pressed ? 0.85 : 1,
            })}
          >
            <View
              style={{
                width: 20,
                height: 20,
                borderRadius: 4,
                borderWidth: 2,
                borderColor: isChecked ? Colors.primary : Colors.textMuted,
                backgroundColor: isChecked ? Colors.primary : 'transparent',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {isChecked && (
                <Text style={{ fontSize: 12, color: Colors.textInverse, fontWeight: FontWeight.bold }}>
                  ✓
                </Text>
              )}
            </View>
            <Text style={{ fontSize: FontSize.sm, color: Colors.text, flex: 1 }}>
              {opt.label}
            </Text>
          </Pressable>
        );
      })}
      {interactive && selected.size > 0 && (
        <SubmitButton label={`Submit (${selected.size})`} onPress={handleSubmit} />
      )}
    </View>
  );
}

// ── Shared sub-components ────────────────────────────────────────────────────

function OptionCard({
  label,
  selected,
  disabled,
  onPress,
  flex,
}: {
  label: string;
  selected: boolean;
  disabled: boolean;
  onPress: () => void;
  flex?: boolean;
}) {
  const Colors = useColors();
  const hapticPress = useHapticPress(onPress);

  return (
    <Pressable
      onPress={disabled ? undefined : hapticPress}
      disabled={disabled}
      style={({ pressed }) => ({
        paddingVertical: Spacing.md,
        paddingHorizontal: Spacing.md,
        borderRadius: BorderRadius.md,
        borderCurve: 'continuous',
        borderWidth: 1.5,
        borderColor: selected ? Colors.primary : Colors.border,
        backgroundColor: selected ? Colors.primary + '10' : Colors.surface,
        opacity: pressed ? 0.85 : disabled && !selected ? 0.5 : 1,
        ...(flex ? { flex: 1, alignItems: 'center' as const } : {}),
      })}
    >
      <Text
        style={{
          fontSize: FontSize.sm,
          fontWeight: selected ? FontWeight.semibold : FontWeight.regular,
          color: selected ? Colors.primary : Colors.text,
          textAlign: flex ? 'center' : 'left',
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function SubmitButton({ label, onPress }: { label: string; onPress: () => void }) {
  const Colors = useColors();

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => ({
        backgroundColor: Colors.primary,
        borderRadius: BorderRadius.md,
        borderCurve: 'continuous',
        paddingVertical: Spacing.sm,
        alignItems: 'center',
        opacity: pressed ? 0.85 : 1,
      })}
    >
      <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.textInverse }}>
        {label}
      </Text>
    </Pressable>
  );
}
