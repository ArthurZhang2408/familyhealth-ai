import { useColorScheme } from 'react-native';
import { LightColors, DarkColors, type ColorPalette } from '@/constants/colors';

export function useColors(): ColorPalette {
  const scheme = useColorScheme();
  return scheme === 'dark' ? DarkColors : LightColors;
}
