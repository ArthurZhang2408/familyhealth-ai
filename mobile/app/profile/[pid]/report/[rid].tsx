import { View, Text, Pressable, Alert } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { ScreenContainer } from '@/components/ScreenContainer';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useReport } from '@/hooks/useReports';
import { reportsApi } from '@/services/api';
import { Colors } from '@/constants/colors';
import { Spacing, FontSize, FontWeight, BorderRadius, Shadow } from '@/constants/theme';
import type { Finding } from '@/types/api';

const STATUS_COLOR = {
  normal: Colors.success,
  low: Colors.info,
  high: Colors.warning,
  critical: Colors.error,
};

function FindingRow({ finding }: { finding: Finding }) {
  const color = STATUS_COLOR[finding.status];
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
  const { pid, rid } = useLocalSearchParams<{ pid: string; rid: string }>();
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
    <>
      <Stack.Screen options={{ title: report.original_filename }} />
      <ScreenContainer contentStyle={{ gap: Spacing.lg }}>
        {/* Status banner */}
        {report.status === 'processing' && (
          <View
            style={{
              backgroundColor: Colors.warningLight,
              borderRadius: BorderRadius.md,
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
                  <FindingRow key={i} finding={f} />
                ))}
              </View>
            )}

            {/* Recommendations */}
            {result.recommendations.length > 0 && (
              <View
                style={{
                  backgroundColor: Colors.surface,
                  borderRadius: BorderRadius.lg,
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
      </ScreenContainer>
    </>
  );
}
