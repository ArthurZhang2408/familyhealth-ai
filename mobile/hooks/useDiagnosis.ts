import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { diagnosisApi } from '@/services/api';

export function useDiagnosisSessions(pid: string) {
  return useQuery({
    queryKey: ['diagnosis', pid],
    queryFn: () => diagnosisApi.list(pid),
    enabled: !!pid,
  });
}

export function useDiagnosisSession(pid: string, sid: string) {
  return useQuery({
    queryKey: ['diagnosis', pid, sid],
    queryFn: () => diagnosisApi.get(pid, sid),
    enabled: !!pid && !!sid,
  });
}

export function useCreateDiagnosisSession(pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (chief_complaint: string) => diagnosisApi.create(pid, chief_complaint),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diagnosis', pid] }),
  });
}

export function useSendDiagnosisMessage(pid: string, sid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => diagnosisApi.sendMessage(pid, sid, content),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['diagnosis', pid, sid] }),
  });
}
