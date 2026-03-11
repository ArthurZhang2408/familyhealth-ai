import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { profilesApi } from '@/services/api';
import type { ProfileCreate, ProfileUpdate } from '@/types/api';

export function useProfiles() {
  return useQuery({
    queryKey: ['profiles'],
    queryFn: () => profilesApi.list(),
  });
}

export function useProfile(pid: string) {
  return useQuery({
    queryKey: ['profiles', pid],
    queryFn: () => profilesApi.get(pid),
    enabled: !!pid,
  });
}

export function useCreateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileCreate) => profilesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles'] }),
  });
}

export function useUpdateProfile(pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileUpdate) => profilesApi.update(pid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles', pid] }),
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pid: string) => profilesApi.remove(pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles'] }),
  });
}
