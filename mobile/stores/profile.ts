import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Profile } from '@/types/api';

interface ProfileState {
  activeProfile: Profile | null;
  setActiveProfile: (profile: Profile | null) => void;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      activeProfile: null,
      setActiveProfile: (profile) => set({ activeProfile: profile }),
    }),
    {
      name: 'profile-store',
      storage: createJSONStorage(() => AsyncStorage),
    },
  ),
);
