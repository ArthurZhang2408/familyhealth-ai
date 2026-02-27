import { View, Text, Pressable, FlatList, Alert } from 'react-native';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import * as Haptics from 'expo-haptics';
import { EmptyState } from '@/components/EmptyState';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { useReports, useUploadReport } from '@/hooks/useReports';
import { Colors } from '@/constants/colors';
import { Spacing, FontSize, FontWeight, BorderRadius, Shadow } from '@/constants/theme';
import type { Report } from '@/types/api';

const STATUS_COLOR: Record<Report['status'], string> = {
  pending: Colors.textMuted,
  processing: Colors.warning,
  complete: Colors.success,
  failed: Colors.error,
};

export default function ReportsScreen() {
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const router = useRouter();
  const { data, isLoading } = useReports(pid);
  const upload = useUploadReport(pid);

  const handleUpload = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'],
      copyToCacheDirectory: true,
    });

    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

    try {
      await upload.mutateAsync({
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType ?? 'application/pdf',
      });
      Alert.alert('Uploaded', 'Your report is being analyzed.');
    } catch (err: unknown) {
      Alert.alert('Upload failed', err instanceof Error ? err.message : 'Unknown error');
    }
  };

  if (isLoading) return <LoadingSpinner />;

  const reports = data?.items ?? [];

  return (
    <>
      <Stack.Screen
        options={{
          title: 'Reports',
          headerRight: () => (
            <Pressable onPress={handleUpload} style={{ marginRight: Spacing.sm }}>
              <Text style={{ fontSize: FontSize.md, color: Colors.primary, fontWeight: FontWeight.semibold }}>
                Upload
              </Text>
            </Pressable>
          ),
        }}
      />
      {reports.length === 0 ? (
        <EmptyState
          title="No reports yet"
          subtitle="Upload a lab report, X-ray, or scan for AI analysis."
          action={
            <Pressable
              onPress={handleUpload}
              style={{
                backgroundColor: Colors.primary,
                borderRadius: BorderRadius.md,
                paddingHorizontal: Spacing.lg,
                paddingVertical: Spacing.sm,
                ...Shadow.sm,
              }}
            >
              <Text style={{ color: Colors.textInverse, fontWeight: FontWeight.semibold }}>
                Upload report
              </Text>
            </Pressable>
          }
        />
      ) : (
        <FlatList
          data={reports}
          keyExtractor={(r) => r.id}
          contentContainerStyle={{ padding: Spacing.md, gap: Spacing.sm }}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => router.push(`/profile/${pid}/report/${item.id}`)}
              style={({ pressed }) => ({
                backgroundColor: Colors.surface,
                borderRadius: BorderRadius.lg,
                padding: Spacing.md,
                opacity: pressed ? 0.85 : 1,
                ...Shadow.sm,
              })}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <Text
                  style={{ fontSize: FontSize.md, fontWeight: FontWeight.semibold, color: Colors.text, flex: 1 }}
                  numberOfLines={1}
                >
                  {item.original_filename}
                </Text>
                <Text
                  style={{
                    fontSize: FontSize.xs,
                    fontWeight: FontWeight.semibold,
                    color: STATUS_COLOR[item.status],
                    textTransform: 'uppercase',
                    marginLeft: Spacing.sm,
                  }}
                >
                  {item.status}
                </Text>
              </View>
              <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: Spacing.xs }}>
                {new Date(item.created_at).toLocaleDateString()}
              </Text>
              {item.analysis_result?.summary && (
                <Text
                  style={{ fontSize: FontSize.sm, color: Colors.text, marginTop: Spacing.xs }}
                  numberOfLines={2}
                >
                  {item.analysis_result.summary}
                </Text>
              )}
            </Pressable>
          )}
        />
      )}
    </>
  );
}
