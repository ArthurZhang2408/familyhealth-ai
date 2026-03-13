import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Profile } from '@/types/api';

interface ProfileState {
  activeProfile: Profile | null;
  setActiveProfile: (profile: Profile | null) => void;
  /** True once AsyncStorage has rehydrated the persisted profile. */
  _hydrated: boolean;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      activeProfile: null,
      setActiveProfile: (profile) => set({ activeProfile: profile }),
      _hydrated: false,
    }),
    {
      name: 'profile-store',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({ activeProfile: state.activeProfile }),
      onRehydrateStorage: () => () => {
        useProfileStore.setState({ _hydrated: true });
      },
    },
  ),
);
