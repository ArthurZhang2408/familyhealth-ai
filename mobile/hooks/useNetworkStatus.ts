import { useEffect, useRef, useState } from 'react';
import NetInfo from '@react-native-community/netinfo';

interface NetworkStatus {
  /** null = unknown (initial state), true = online, false = offline */
  isConnected: boolean | null;
}

/**
 * Thin wrapper around NetInfo with 1s debounce to prevent flicker on cellular.
 * Only reports offline after 1 continuous second of disconnection.
 */
export function useNetworkStatus(): NetworkStatus {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      const connected = state.isConnected ?? null;

      if (connected === false) {
        // Debounce: only report offline after 1s of continuous disconnection
        if (!timerRef.current) {
          timerRef.current = setTimeout(() => {
            setIsConnected(false);
            timerRef.current = null;
          }, 1000);
        }
      } else {
        // Online: clear any pending debounce and update immediately
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        setIsConnected(connected);
      }
    });

    return () => {
      unsubscribe();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { isConnected };
}
