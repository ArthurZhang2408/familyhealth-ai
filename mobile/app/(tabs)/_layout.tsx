import { Text } from 'react-native';
import { Tabs } from 'expo-router';
import { Colors } from '@/constants/colors';
import { FontSize } from '@/constants/theme';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarStyle: {
          backgroundColor: Colors.surface,
          borderTopColor: Colors.border,
        },
        tabBarLabelStyle: {
          fontSize: FontSize.xs,
          fontWeight: '600',
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, size }) => (
            // Using a simple text glyph — swap for expo-image SF Symbols when building for iOS
            <TabIcon label="⊡" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color, size }) => (
            <TabIcon label="⚙" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}

function TabIcon({ label, color }: { label: string; color: string; size: number }) {
  return <Text style={{ fontSize: 20, color }}>{label}</Text>;
}
