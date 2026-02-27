import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { reportsApi } from '@/services/api';

export function useReports(pid: string) {
  return useQuery({
    queryKey: ['reports', pid],
    queryFn: () => reportsApi.list(pid),
    enabled: !!pid,
  });
}

export function useReport(pid: string, rid: string) {
  return useQuery({
    queryKey: ['reports', pid, rid],
    queryFn: () => reportsApi.get(pid, rid),
    enabled: !!pid && !!rid,
  });
}

export function useUploadReport(pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: { uri: string; name: string; type: string }) =>
      reportsApi.upload(pid, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports', pid] }),
  });
}
