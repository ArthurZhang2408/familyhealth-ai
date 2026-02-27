import { create } from 'zustand';
import type { Profile } from '@/types/api';

interface ProfileState {
  activeProfile: Profile | null;
  setActiveProfile: (profile: Profile | null) => void;
}

export const useProfileStore = create<ProfileState>((set) => ({
  activeProfile: null,
  setActiveProfile: (profile) => set({ activeProfile: profile }),
}));
