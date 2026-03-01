import { useEffect } from 'react';
import { Drawer } from 'expo-router/drawer';
import { SidebarContent } from '@/components/SidebarContent';
import { ProfilePill } from '@/components/ProfilePill';
import { HeaderBar } from '@/components/HeaderBar';
import { HeaderIconButton } from '@/components/HeaderIconButton';
import { useProfileStore } from '@/stores/profile';
import { useProfiles } from '@/hooks/useProfiles';
import { useColors } from '@/hooks/useColors';

export default function MainLayout() {
  const Colors = useColors();
  const activeProfile = useProfileStore((s) => s.activeProfile);
  const setActiveProfile = useProfileStore((s) => s.setActiveProfile);
  const { data } = useProfiles();

  useEffect(() => {
    if (!activeProfile && data?.items && data.items.length > 0) {
      setActiveProfile(data.items[0]);
    }
  }, [activeProfile, data, setActiveProfile]);

  return (
    <Drawer
      drawerContent={(props) => <SidebarContent {...props} />}
      screenOptions={({ navigation }) => ({
        drawerStyle: {
          width: 280,
          backgroundColor: Colors.surface,
        },
        header: ({ options }) => (
          <HeaderBar
            left={<HeaderIconButton icon="menu" onPress={() => navigation.toggleDrawer()} />}
            center={<ProfilePill />}
            right={options.headerRight?.({ canGoBack: false })}
          />
        ),
        sceneStyle: { backgroundColor: Colors.background },
      })}
    >
      <Drawer.Screen name="index" options={{ drawerItemStyle: { display: 'none' } }} />
      <Drawer.Screen name="chat/[cid]" options={{ drawerItemStyle: { display: 'none' } }} />
      <Drawer.Screen name="diagnosis/[sid]" options={{ drawerItemStyle: { display: 'none' } }} />
      <Drawer.Screen name="diagnosis/past" options={{ drawerItemStyle: { display: 'none' } }} />
      <Drawer.Screen name="report/[rid]" options={{ drawerItemStyle: { display: 'none' } }} />
    </Drawer>
  );
}
