import { useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { Icon } from '@/components/Icon';
import type { MessagePart } from '@/types/api';

type ToolCallPart = Extract<MessagePart, { type: 'tool_call' }>;
type ToolResultPart = Extract<MessagePart, { type: 'tool_result' }>;

const TOOL_LABELS: Record<string, string> = {
  web_search: 'Web Search',
  search_patient_memory: 'Memory Search',
  present_question: 'Question',
  profile_lookup: 'Profile Lookup',
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, ' ');
}

export function ToolCallPartView({ call, result }: { call: ToolCallPart; result?: ToolResultPart }) {
  const Colors = useColors();
  const [expanded, setExpanded] = useState(false);

  const statusColor = result?.is_error ? Colors.error : Colors.success;
  const statusIcon = result?.is_error ? 'close-circle' : 'checkmark-circle';

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
        <Icon name={statusIcon} size={14} color={statusColor} />
        <Text
          style={{ fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: FontWeight.medium, flex: 1 }}
          numberOfLines={1}
        >
          {toolLabel(call.name)}
        </Text>
        {result?.summary && (
          <Text style={{ fontSize: FontSize.xs - 1, color: Colors.textMuted }} numberOfLines={1}>
            {result.summary}
          </Text>
        )}
        <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={12} color={Colors.textMuted} />
      </Pressable>
      {expanded && (
        <View style={{ padding: Spacing.sm, backgroundColor: Colors.surfaceSecondary, gap: Spacing.xs }}>
          <Text style={{ fontSize: FontSize.xs - 1, color: Colors.textMuted, fontWeight: FontWeight.medium }}>
            Arguments
          </Text>
          <Text
            style={{ fontSize: FontSize.xs - 1, color: Colors.textSecondary, fontFamily: 'monospace' }}
            selectable
          >
            {JSON.stringify(call.arguments, null, 2)}
          </Text>
          {result && (
            <>
              <Text style={{ fontSize: FontSize.xs - 1, color: Colors.textMuted, fontWeight: FontWeight.medium, marginTop: Spacing.xs }}>
                Result
              </Text>
              <Text
                style={{ fontSize: FontSize.xs - 1, color: Colors.textSecondary, fontFamily: 'monospace' }}
                selectable
              >
                {JSON.stringify(result.output, null, 2)}
              </Text>
            </>
          )}
        </View>
      )}
    </View>
  );
}
