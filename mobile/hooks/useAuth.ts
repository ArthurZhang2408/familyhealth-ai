import { useEffect } from 'react';
import { supabase } from '@/services/supabase';
import { useAuthStore } from '@/stores/auth';
import { useProfileStore } from '@/stores/profile';

export function useAuth() {
  const { session, user, loading, setSession, setLoading } = useAuthStore();

  useEffect(() => {
    // Load initial session
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    // Listen for auth state changes
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      const prevUid = useAuthStore.getState().user?.id;
      const nextUid = newSession?.user?.id;
      // Clear persisted profile when user changes (sign-out or switch account)
      if (prevUid !== nextUid) {
        useProfileStore.getState().setActiveProfile(null);
      }
      setSession(newSession);
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  return { session, user, loading, isAuthenticated: !!session };
}
