import { useEffect } from 'react';
import { AppState, Platform, useColorScheme } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuth } from '@/hooks/useAuth';
import { useColors } from '@/hooks/useColors';
import { ErrorBoundary } from '@/components/ErrorBoundary';

// Keep splash screen visible until auth state is determined
SplashScreen.preventAutoHideAsync();

// Refetch active queries when app comes back from background.
// This ensures server-persisted data (from interrupted streams) shows up.
focusManager.setEventListener((handleFocus) => {
  const subscription = AppState.addEventListener('change', (state) => {
    if (Platform.OS !== 'web') {
      handleFocus(state === 'active');
    }
  });
  return () => subscription.remove();
});

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

    // Auth state determined — hide splash screen
    SplashScreen.hideAsync();

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
      <KeyboardProvider>
        <QueryClientProvider client={queryClient}>
          <AuthGuard />
          <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
          <ErrorBoundary>
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
              name="profile/new"
              options={{
                presentation: 'modal',
                headerShown: true,
                headerTitle: 'New Profile',
                headerStyle: { backgroundColor: Colors.surface },
                headerTintColor: Colors.text,
                headerShadowVisible: false,
                contentStyle: { backgroundColor: Colors.surface },
              }}
            />
          </Stack>
          </ErrorBoundary>
        </QueryClientProvider>
      </KeyboardProvider>
    </GestureHandlerRootView>
  );
}
