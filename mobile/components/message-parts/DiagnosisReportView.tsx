import { useState } from 'react';
import { View, Text, Pressable, Linking } from 'react-native';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import { Icon } from '@/components/Icon';
import type { MessagePart, AssessmentCondition, AssessmentMedication, AssessmentAction, AssessmentTest, AssessmentSource } from '@/types/api';

type AssessmentPart = Extract<MessagePart, { type: 'assessment' }>;

// ── Confidence styling ──────────────────────────────────────────────────
// Left-border accent conveys likelihood at a glance without noisy badges.

const CONFIDENCE_META: Record<string, { label: string; rank: string }> = {
  most_likely: { label: 'Most likely', rank: '1' },
  possible:    { label: 'Possible',    rank: '2' },
  less_likely: { label: 'Less likely', rank: '3' },
};

function useConfidenceColor(confidence: string) {
  const C = useColors();
  switch (confidence) {
    case 'most_likely': return C.primary;
    case 'possible':    return C.warning;
    default:            return C.textMuted;
  }
}

// ── Main Component ──────────────────────────────────────────────────────

export function DiagnosisReportView({ part }: { part: AssessmentPart }) {
  const Colors = useColors();
  const shadow = useShadow();
  const hasActions = part.medications.length > 0 || part.self_care.length > 0;

  // Derive triage urgency from assessment content
  const hasWarnings = part.warnings.length > 0;
  const topConfidence = part.conditions[0]?.confidence;
  const triage = hasWarnings && topConfidence === 'most_likely'
    ? 'schedule' // amber — see a doctor
    : hasWarnings
      ? 'caution' // amber
      : 'self_care'; // green — likely manageable

  return (
    <View style={{ marginTop: Spacing.sm, gap: Spacing.md }}>
      {/* ── Triage Banner ──────────────────────────────────── */}
      <TriageBanner triage={triage} Colors={Colors} />

      {/* ── Conditions (expandable) ────────────────────────── */}
      {part.conditions.map((cond, i) => (
        <ConditionCard key={i} condition={cond} defaultExpanded={i === 0} Colors={Colors} shadow={shadow} />
      ))}

      {/* ── What You Can Do Now (meds + self-care unified) ── */}
      {hasActions && (
        <ActionSection
          medications={part.medications}
          selfCare={part.self_care}
          Colors={Colors}
          shadow={shadow}
        />
      )}

      {/* ── Warnings — always visible, safety-critical ───── */}
      {part.warnings.length > 0 && (
        <WarningsCard warnings={part.warnings} Colors={Colors} />
      )}

      {/* ── Tests (collapsible, collapsed by default) ────── */}
      {part.tests.length > 0 && (
        <TestsSection tests={part.tests} Colors={Colors} shadow={shadow} />
      )}

      {/* ── Follow-up (inline) ─────────────────────────────── */}
      {part.follow_up && (
        <View style={{ paddingHorizontal: Spacing.xs }}>
          <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 }}>
            <Text style={{ fontWeight: FontWeight.semibold, color: Colors.text }}>Follow-up: </Text>
            {part.follow_up}
          </Text>
        </View>
      )}

      {/* ── Sources ────────────────────────────────────────── */}
      {part.sources && part.sources.length > 0 && (
        <SourcesList sources={part.sources} Colors={Colors} />
      )}
    </View>
  );
}

// ── Condition Card ──────────────────────────────────────────────────────
// Collapsed: name + confidence label + chevron.  Expanded: + reasoning + tests.
// First condition expanded by default (the primary diagnosis).

function ConditionCard({
  condition,
  defaultExpanded,
  Colors,
  shadow,
}: {
  condition: AssessmentCondition;
  defaultExpanded: boolean;
  Colors: ReturnType<typeof useColors>;
  shadow: ReturnType<typeof useShadow>;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const accentColor = useConfidenceColor(condition.confidence);
  const meta = CONFIDENCE_META[condition.confidence] ?? CONFIDENCE_META.possible;

  return (
    <Pressable onPress={() => setExpanded((p) => !p)}>
      <View
        style={{
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          backgroundColor: Colors.surface,
          borderWidth: 1,
          borderColor: Colors.border,
          overflow: 'hidden',
          ...shadow,
        }}
      >
        {/* Colored top accent bar */}
        <View style={{ height: 3, backgroundColor: accentColor }} />

        {/* Header — always visible */}
        <View style={{ padding: Spacing.md, paddingBottom: expanded ? Spacing.sm : Spacing.md }}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.bold, color: Colors.text }}>
                {condition.name}
              </Text>
              <Text style={{ fontSize: FontSize.xs, color: accentColor, fontWeight: FontWeight.medium }}>
                {meta.label}
              </Text>
            </View>
            <Icon
              name={expanded ? 'chevron-up' : 'chevron-down'}
              size={16}
              color={Colors.textMuted}
            />
          </View>
        </View>

        {/* Body — expanded only */}
        {expanded && (
          <View style={{
            paddingHorizontal: Spacing.md,
            paddingBottom: Spacing.md,
            borderTopWidth: 1,
            borderTopColor: Colors.border,
            paddingTop: Spacing.sm,
          }}>
            <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 }}>
              {condition.reasoning}
            </Text>
            {condition.confirming_tests && (
              <View style={{
                marginTop: Spacing.sm,
                backgroundColor: Colors.surfaceSecondary,
                borderRadius: BorderRadius.sm,
                borderCurve: 'continuous',
                padding: Spacing.sm,
              }}>
                <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>
                  <Text style={{ fontWeight: FontWeight.semibold }}>To confirm: </Text>
                  {condition.confirming_tests}
                </Text>
              </View>
            )}
          </View>
        )}
      </View>
    </Pressable>
  );
}

// ── Action Section (What You Can Do Now) ────────────────────────────────
// Unified section: medications are prominent, self-care follows.
// Always expanded — this is the most actionable part of the assessment.

function ActionSection({
  medications,
  selfCare,
  Colors,
  shadow,
}: {
  medications: AssessmentMedication[];
  selfCare: AssessmentAction[];
  Colors: ReturnType<typeof useColors>;
  shadow: ReturnType<typeof useShadow>;
}) {
  return (
    <View
      style={{
        borderRadius: BorderRadius.md,
        borderCurve: 'continuous',
        backgroundColor: Colors.surface,
        borderWidth: 1,
        borderColor: Colors.border,
        overflow: 'hidden',
        ...shadow,
      }}
    >
      {/* Header */}
      <View style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: Spacing.sm,
        padding: Spacing.md,
        paddingBottom: Spacing.sm,
        borderBottomWidth: 1,
        borderBottomColor: Colors.border,
      }}>
        <View style={{
          width: 28,
          height: 28,
          borderRadius: BorderRadius.full,
          backgroundColor: `${Colors.success}15`,
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <Icon name="checkmark-circle" size={16} color={Colors.success} />
        </View>
        <Text style={{ fontSize: FontSize.md, fontWeight: FontWeight.bold, color: Colors.text }}>
          What You Can Do Now
        </Text>
      </View>

      <View style={{ padding: Spacing.md, gap: Spacing.md }}>
        {/* Medications */}
        {medications.length > 0 && (
          <View style={{ gap: Spacing.sm }}>
            {medications.map((med, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: Spacing.sm }}>
                <View style={{ marginTop: 2 }}>
                  <Icon name="medkit" size={14} color={Colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: FontSize.sm, color: Colors.text }}>
                    <Text style={{ fontWeight: FontWeight.semibold }}>{med.name}</Text>
                    {'  '}
                    <Text style={{ color: Colors.textSecondary }}>{med.dosage}</Text>
                  </Text>
                  {med.notes && (
                    <Text style={{ fontSize: FontSize.xs, color: Colors.warning, marginTop: 1 }}>
                      {med.notes}
                    </Text>
                  )}
                </View>
              </View>
            ))}
          </View>
        )}

        {/* Divider between meds and self-care */}
        {medications.length > 0 && selfCare.length > 0 && (
          <View style={{ height: 1, backgroundColor: Colors.border }} />
        )}

        {/* Self-care */}
        {selfCare.length > 0 && (
          <View style={{ gap: Spacing.xs }}>
            {selfCare.map((item, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: Spacing.sm }}>
                <Text style={{ fontSize: FontSize.sm, color: Colors.success, marginTop: 1 }}>•</Text>
                <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary, flex: 1, lineHeight: 20 }}>
                  {item.action}{item.detail ? ` — ${item.detail}` : ''}
                </Text>
              </View>
            ))}
          </View>
        )}
      </View>
    </View>
  );
}

// ── Warnings Card ───────────────────────────────────────────────────────
// Always visible. Red accent. Clear, non-panicky.

function WarningsCard({
  warnings,
  Colors,
}: {
  warnings: string[];
  Colors: ReturnType<typeof useColors>;
}) {
  return (
    <View style={{
      borderRadius: BorderRadius.md,
      borderCurve: 'continuous',
      borderWidth: 1,
      borderColor: `${Colors.error}30`,
      backgroundColor: `${Colors.error}06`,
      overflow: 'hidden',
    }}>
      {/* Red top bar */}
      <View style={{ height: 3, backgroundColor: Colors.error }} />

      <View style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: Spacing.sm,
        padding: Spacing.md,
        paddingBottom: Spacing.sm,
      }}>
        <Icon name="alert-circle" size={16} color={Colors.error} />
        <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.bold, color: Colors.error }}>
          Seek care if
        </Text>
      </View>

      <View style={{ paddingHorizontal: Spacing.md, paddingBottom: Spacing.md, gap: Spacing.xs }}>
        {warnings.map((w, i) => (
          <View key={i} style={{ flexDirection: 'row', gap: Spacing.sm }}>
            <Text style={{ fontSize: FontSize.sm, color: Colors.error, lineHeight: 20 }}>•</Text>
            <Text style={{ fontSize: FontSize.sm, color: Colors.text, flex: 1, lineHeight: 20 }}>
              {w}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ── Tests Section ───────────────────────────────────────────────────────
// Collapsed by default — this info is for the doctor visit, not immediate.

function TestsSection({
  tests,
  Colors,
  shadow,
}: {
  tests: AssessmentTest[];
  Colors: ReturnType<typeof useColors>;
  shadow: ReturnType<typeof useShadow>;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Pressable onPress={() => setExpanded((p) => !p)}>
      <View
        style={{
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          backgroundColor: Colors.surface,
          borderWidth: 1,
          borderColor: Colors.border,
          overflow: 'hidden',
          ...shadow,
        }}
      >
        {/* Header — always visible */}
        <View style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: Spacing.sm,
          padding: Spacing.md,
        }}>
          <Icon name="flask" size={14} color={Colors.primary} />
          <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.text, flex: 1 }}>
            {tests.length} test{tests.length !== 1 ? 's' : ''} to discuss with your doctor
          </Text>
          <Icon
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={14}
            color={Colors.textMuted}
          />
        </View>

        {/* Body — expanded only */}
        {expanded && (
          <View style={{
            paddingHorizontal: Spacing.md,
            paddingBottom: Spacing.md,
            borderTopWidth: 1,
            borderTopColor: Colors.border,
            paddingTop: Spacing.sm,
            gap: Spacing.sm,
          }}>
            {tests.map((test, i) => (
              <View key={i}>
                <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.text }}>
                  {test.name}
                </Text>
                <Text style={{ fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 18 }}>
                  {test.reason}
                </Text>
                {test.urgency && (
                  <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted, fontStyle: 'italic' }}>
                    {test.urgency}
                  </Text>
                )}
              </View>
            ))}
          </View>
        )}
      </View>
    </Pressable>
  );
}

// ── Triage Banner ───────────────────────────────────────────────────────
// Leads the assessment. One line summarizing urgency level.

type TriageLevel = 'self_care' | 'schedule' | 'caution';

const TRIAGE_CONFIG: Record<TriageLevel, { message: string; colorKey: 'success' | 'warning' }> = {
  self_care: { message: 'Likely manageable with self-care', colorKey: 'success' },
  schedule:  { message: 'Consider scheduling a doctor visit', colorKey: 'warning' },
  caution:   { message: 'Monitor closely — see warning signs below', colorKey: 'warning' },
};

function TriageBanner({
  triage,
  Colors,
}: {
  triage: TriageLevel;
  Colors: ReturnType<typeof useColors>;
}) {
  const config = TRIAGE_CONFIG[triage];
  const color = Colors[config.colorKey];

  return (
    <View style={{
      flexDirection: 'row',
      alignItems: 'center',
      gap: Spacing.sm,
      paddingVertical: Spacing.sm,
      paddingHorizontal: Spacing.md,
      borderRadius: BorderRadius.md,
      borderCurve: 'continuous',
      backgroundColor: `${color}12`,
      borderWidth: 1,
      borderColor: `${color}30`,
    }}>
      <Icon
        name={triage === 'self_care' ? 'checkmark-circle' : 'alert-circle'}
        size={18}
        color={color}
      />
      <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color, flex: 1 }}>
        {config.message}
      </Text>
    </View>
  );
}

// ── Sources ─────────────────────────────────────────────────────────────

function SourcesList({
  sources,
  Colors,
}: {
  sources: AssessmentSource[];
  Colors: ReturnType<typeof useColors>;
}) {
  return (
    <View style={{ gap: 2 }}>
      {sources.map((src, i) => (
        <Pressable key={i} onPress={() => Linking.openURL(src.url)} hitSlop={4}>
          <Text style={{ fontSize: FontSize.xs - 1, color: Colors.textMuted, lineHeight: 16 }}>
            [{i + 1}]{' '}
            <Text style={{ color: Colors.primary, textDecorationLine: 'underline' }}>
              {src.title}
            </Text>
          </Text>
        </Pressable>
      ))}
    </View>
  );
}
