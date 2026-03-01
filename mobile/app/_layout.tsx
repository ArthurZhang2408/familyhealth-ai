import { useEffect } from 'react';
import { useColorScheme } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuth } from '@/hooks/useAuth';
import { useColors } from '@/hooks/useColors';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 min
      retry: 1,
    },
  },
});

function AuthGuard() {
  const { isAuthenticated, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;

    const inAuthGroup = segments[0] === '(auth)';

    if (!isAuthenticated && !inAuthGroup) {
      queryClient.clear();
      router.replace('/(auth)/login');
    } else if (isAuthenticated && inAuthGroup) {
      router.replace('/(main)');
    }
  }, [isAuthenticated, loading, segments, router]);

  return null;
}

export default function RootLayout() {
  const Colors = useColors();
  const scheme = useColorScheme();

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: Colors.background }}>
      <QueryClientProvider client={queryClient}>
        <AuthGuard />
        <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Colors.background } }}>
          <Stack.Screen name="(auth)" />
          <Stack.Screen name="(main)" />
          <Stack.Screen
            name="settings"
            options={{
              presentation: 'formSheet',
              sheetGrabberVisible: true,
              sheetAllowedDetents: [0.85],
              headerShown: true,
              headerTitle: 'Settings',
              headerStyle: { backgroundColor: Colors.surface },
              headerTintColor: Colors.text,
              headerShadowVisible: false,
            }}
          />
          <Stack.Screen
            name="profile-picker"
            options={{
              presentation: 'formSheet',
              sheetGrabberVisible: true,
              sheetAllowedDetents: [0.5, 0.85],
              headerShown: true,
              headerTitle: 'Select Profile',
              headerStyle: { backgroundColor: Colors.surface },
              headerTintColor: Colors.text,
              headerShadowVisible: false,
            }}
          />
          <Stack.Screen
            name="profile/new"
            options={{
              presentation: 'formSheet',
              sheetGrabberVisible: true,
              sheetAllowedDetents: [0.7, 1.0],
              headerShown: true,
              headerTitle: 'New Profile',
              headerStyle: { backgroundColor: Colors.surface },
              headerTintColor: Colors.text,
              headerShadowVisible: false,
            }}
          />
        </Stack>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}
