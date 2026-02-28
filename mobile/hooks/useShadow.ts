import { useColorScheme } from 'react-native';

const lightShadows = {
  sm: { boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)' },
  md: { boxShadow: '0 4px 6px rgba(0, 0, 0, 0.07)' },
  lg: { boxShadow: '0 10px 15px rgba(0, 0, 0, 0.1)' },
} as const;

// In dark mode shadows are invisible — use subtle border glow instead
const darkShadows = {
  sm: { boxShadow: '0 0 0 1px rgba(255, 255, 255, 0.06)' },
  md: { boxShadow: '0 0 0 1px rgba(255, 255, 255, 0.08)' },
  lg: { boxShadow: '0 0 0 1px rgba(255, 255, 255, 0.10)' },
} as const;

export function useShadow() {
  const scheme = useColorScheme();
  return scheme === 'dark' ? darkShadows : lightShadows;
}
