import { Stack } from 'expo-router';
import { useColors } from '@/hooks/useColors';

export default function AuthLayout() {
  const Colors = useColors();
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: Colors.background },
        animation: 'fade',
      }}
    />
  );
}
