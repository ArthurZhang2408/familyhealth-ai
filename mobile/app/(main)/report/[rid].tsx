import { useMemo } from 'react';
import { View, Text, Pressable, Alert, ScrollView } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { NoProfileGuard } from '@/components/NoProfileGuard';
import { useProfileStore } from '@/stores/profile';
import { useReport } from '@/hooks/useReports';
import { reportsApi } from '@/services/api';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type { ColorPalette } from '@/constants/colors';
import type { Finding } from '@/types/api';

function FindingRow({ finding, colors: Colors }: { finding: Finding; colors: ColorPalette }) {
  const statusColor: Record<string, string> = useMemo(() => ({
    normal: Colors.success,
    low: Colors.info,
    high: Colors.warning,
    critical: Colors.error,
  }), [Colors]);

  const color = statusColor[finding.status];
  return (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: Spacing.sm,
        borderBottomWidth: 1,
        borderBottomColor: Colors.border,
      }}
    >
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.medium, color: Colors.text }}>
          {finding.name}
        </Text>
        {finding.reference_range && (
          <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>
            Ref: {finding.reference_range}
          </Text>
        )}
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color }}>
          {finding.value} {finding.unit ?? ''}
        </Text>
        <Text style={{ fontSize: FontSize.xs, color, textTransform: 'uppercase' }}>
          {finding.status}
        </Text>
      </View>
    </View>
  );
}

export default function ReportDetailScreen() {
  const Colors = useColors();
  const Shadow = useShadow();
  const { rid } = useLocalSearchParams<{ rid: string }>();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const pid = activeProfile?.id ?? '';

  const { data: report, isLoading, refetch } = useReport(pid, rid);

  const handleReanalyze = async () => {
    try {
      await reportsApi.reanalyze(pid, rid);
      refetch();
      Alert.alert('Re-analysis started', 'Check back shortly for updated results.');
    } catch (err: unknown) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Unknown error');
    }
  };

  if (isLoading) return <LoadingSpinner />;
  if (!report) return null;

  const result = report.analysis_result;

  return (
    <NoProfileGuard>
      <Stack.Screen options={{ title: report.original_filename }} />
      <ScrollView
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={{ padding: Spacing.md, gap: Spacing.lg, paddingBottom: Spacing.xxl }}
        style={{ flex: 1, backgroundColor: Colors.background }}
      >
        {/* Status banner */}
        {report.status === 'processing' && (
          <View
            style={{
              backgroundColor: Colors.warningLight,
              borderRadius: BorderRadius.md,
              borderCurve: 'continuous',
              padding: Spacing.md,
            }}
          >
            <Text style={{ fontSize: FontSize.sm, color: Colors.warning, fontWeight: FontWeight.semibold }}>
              Analysis in progress…
            </Text>
          </View>
        )}

        {report.status === 'failed' && (
          <View
            style={{
              backgroundColor: Colors.errorLight,
              borderRadius: BorderRadius.md,
              borderCurve: 'continuous',
              padding: Spacing.md,
              gap: Spacing.sm,
            }}
          >
            <Text style={{ fontSize: FontSize.sm, color: Colors.error }}>
              {report.error_message ?? 'Analysis failed.'}
            </Text>
            <Pressable onPress={handleReanalyze}>
              <Text style={{ fontSize: FontSize.sm, color: Colors.error, fontWeight: FontWeight.semibold }}>
                Try again →
              </Text>
            </Pressable>
          </View>
        )}

        {result && (
          <>
            {/* Summary */}
            <View
              style={{
                backgroundColor: Colors.surface,
                borderRadius: BorderRadius.lg,
                borderCurve: 'continuous',
                padding: Spacing.lg,
                ...Shadow.sm,
              }}
            >
              <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.textMuted, marginBottom: Spacing.xs }}>
                SUMMARY
              </Text>
              <Text style={{ fontSize: FontSize.md, color: Colors.text, lineHeight: 22 }} selectable>
                {result.summary}
              </Text>
            </View>

            {/* Alerts */}
            {result.alerts.length > 0 && (
              <View
                style={{
                  backgroundColor: Colors.errorLight,
                  borderRadius: BorderRadius.lg,
                  borderCurve: 'continuous',
                  padding: Spacing.md,
                  gap: Spacing.xs,
                }}
              >
                <Text style={{ fontSize: FontSize.sm, fontWeight: FontWeight.semibold, color: Colors.error }}>
                  ALERTS
                </Text>
                {result.alerts.map((alert, i) => (
                  <Text key={i} style={{ fontSize: FontSize.sm, color: Colors.text }} selectable>
                    • {alert}
                  </Text>
                ))}
              </View>
            )}

            {/* Findings */}
            {result.findings.length > 0 && (
              <View
                style={{
                  backgroundColor: Colors.surface,
                  borderRadius: BorderRadius.lg,
                  borderCurve: 'continuous',
                  padding: Spacing.md,
                  ...Shadow.sm,
                }}
              >
                <Text
                  style={{
                    fontSize: FontSize.sm,
                    fontWeight: FontWeight.semibold,
                    color: Colors.textMuted,
                    marginBottom: Spacing.sm,
                  }}
                >
                  FINDINGS
                </Text>
                {result.findings.map((f, i) => (
                  <FindingRow key={i} finding={f} colors={Colors} />
                ))}
              </View>
            )}

            {/* Recommendations */}
            {result.recommendations.length > 0 && (
              <View
                style={{
                  backgroundColor: Colors.surface,
                  borderRadius: BorderRadius.lg,
                  borderCurve: 'continuous',
                  padding: Spacing.md,
                  ...Shadow.sm,
                }}
              >
                <Text
                  style={{
                    fontSize: FontSize.sm,
                    fontWeight: FontWeight.semibold,
                    color: Colors.textMuted,
                    marginBottom: Spacing.sm,
                  }}
                >
                  RECOMMENDATIONS
                </Text>
                {result.recommendations.map((rec, i) => (
                  <Text key={i} style={{ fontSize: FontSize.sm, color: Colors.text, marginBottom: Spacing.xs }} selectable>
                    • {rec}
                  </Text>
                ))}
              </View>
            )}
          </>
        )}

        {/* Disclaimer */}
        {report.disclaimer && (
          <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted, textAlign: 'center' }} selectable>
            {report.disclaimer}
          </Text>
        )}
      </ScrollView>
    </NoProfileGuard>
  );
}
