import { useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi, diagnosisApi } from '@/services/api';

export type SessionType = 'chat' | 'diagnosis';

export function useDeleteSession(type: SessionType, pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      type === 'chat' ? chatApi.delete(pid, id) : diagnosisApi.delete(pid, id),
    onSuccess: (_data, id) => {
      // Set deleted item's data to null instead of removeQueries.
      // removeQueries forces mounted screens (Drawer keeps them alive)
      // to re-create the query and refetch → 404 spam.
      // setQueryData(null) keeps the query in cache with null data so
      // React Query won't refetch, and the screen shows loading state.
      qc.cancelQueries({ queryKey: [type, pid, id] });
      qc.setQueryData([type, pid, id], null);
      // exact: true → only invalidate the list query, not individual
      // conversation queries for other mounted screens.
      qc.invalidateQueries({ queryKey: [type, pid], exact: true });
    },
  });
}

export function useRenameSession(type: SessionType, pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) => {
      if (type === 'chat') await chatApi.rename(pid, id, title);
      else await diagnosisApi.rename(pid, id, title);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: [type, pid], exact: true }),
  });
}
