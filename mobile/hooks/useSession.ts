import { useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi, diagnosisApi } from '@/services/api';

export type SessionType = 'chat' | 'diagnosis';

export function useDeleteSession(type: SessionType, pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      type === 'chat' ? chatApi.delete(pid, id) : diagnosisApi.delete(pid, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: [type, pid] }),
  });
}

export function useRenameSession(type: SessionType, pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) => {
      if (type === 'chat') await chatApi.rename(pid, id, title);
      else await diagnosisApi.rename(pid, id, title);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: [type, pid] }),
  });
}
