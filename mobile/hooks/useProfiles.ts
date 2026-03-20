import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { profilesApi } from '@/services/api';
import { useAuth } from '@/hooks/useAuth';
import { useProfileStore } from '@/stores/profile';
import type { ProfileCreate, ProfileUpdate } from '@/types/api';

export function useProfiles() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['profiles'],
    queryFn: () => profilesApi.list(),
    enabled: isAuthenticated,
  });
}

export function useProfile(pid: string) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['profiles', pid],
    queryFn: () => profilesApi.get(pid),
    enabled: isAuthenticated && !!pid,
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
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const setActiveProfile = useProfileStore((s) => s.setActiveProfile);
  return useMutation({
    mutationFn: (body: ProfileUpdate) => profilesApi.update(pid, body),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ['profiles', pid] });
      qc.invalidateQueries({ queryKey: ['profiles'] });
      if (activeProfile?.id === pid) setActiveProfile(updated);
    },
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pid: string) => profilesApi.remove(pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles'] }),
  });
}
