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
  /** pre-select mode on the new conversation screen ('chat' | 'diagnosis') */
  pendingMode: 'chat' | 'diagnosis' | null;
  setPendingMode: (value: 'chat' | 'diagnosis' | null) => void;
}

export const useNavSource = create<NavSourceState>((set) => ({
  fromList: false,
  setFromList: (value) => set({ fromList: value }),
  pendingMode: null,
  setPendingMode: (value) => set({ pendingMode: value }),
}));
