/**
 * Tracks navigation source for session screens.
 *
 * Zustand-based: reactive (triggers re-renders), synchronous,
 * and doesn't depend on unreliable focus/blur events in Drawer navigators.
 */
import { create } from 'zustand';

interface NavSourceState {
  /** true when navigating from a list page (all chats / all sessions) */
  fromList: boolean;
  setFromList: (value: boolean) => void;
}

export const useNavSource = create<NavSourceState>((set) => ({
  fromList: false,
  setFromList: (value) => set({ fromList: value }),
}));
