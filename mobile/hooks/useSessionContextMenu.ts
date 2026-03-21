import { useState, useCallback } from 'react';
import { Alert } from 'react-native';
import * as Haptics from 'expo-haptics';
import { useDeleteSession, useRenameSession, SessionType } from '@/hooks/useSession';
import { ContextMenuState, MENU_INITIAL, MenuAction } from '@/components/ContextMenuOverlay';

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'object' && err !== null && 'message' in err) return String((err as any).message);
  return fallback;
}

export function useSessionContextMenu(
  pid: string,
  opts?: { onDelete?: (type: SessionType, id: string) => void },
) {
  const [menu, setMenu] = useState<ContextMenuState>(MENU_INITIAL);
  const dismissMenu = useCallback(() => setMenu(MENU_INITIAL), []);

  const renameChat = useRenameSession('chat', pid);
  const deleteChat = useDeleteSession('chat', pid);
  const renameDx = useRenameSession('diagnosis', pid);
  const deleteDx = useDeleteSession('diagnosis', pid);

  const openMenu = useCallback(
    (
      type: SessionType,
      id: string,
      title: string,
      x: number, y: number, w: number, h: number,
    ) => {
      if (process.env.EXPO_OS === 'ios') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

      const rename = type === 'chat' ? renameChat : renameDx;
      const del = type === 'chat' ? deleteChat : deleteDx;
      const typeLabel = type === 'chat' ? 'Conversation' : 'Session';

      const actions: MenuAction[] = [
        {
          label: 'Rename', icon: 'pencil',
          onPress: () => {
            dismissMenu();
            setTimeout(() => {
              Alert.prompt(`Rename ${typeLabel}`, undefined, (t) => {
                if (!t?.trim()) {
                  if (t != null) Alert.alert('Name required', 'Please enter a name.');
                  return;
                }
                rename.mutate(
                  { id, title: t.trim() },
                  { onError: (e) => Alert.alert('Rename failed', errorMessage(e, 'Please try again.')) },
                );
              }, 'plain-text', title);
            }, 150);
          },
        },
        {
          label: 'Delete', icon: 'trash', destructive: true,
          onPress: () => {
            dismissMenu();
            setTimeout(() => {
              Alert.alert(`Delete ${typeLabel}`, 'This will also remove memories from this session.', [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Delete', style: 'destructive',
                  onPress: () => {
                    del.mutate(id, {
                      onSuccess: () => opts?.onDelete?.(type, id),
                      onError: (e) => Alert.alert('Delete failed', errorMessage(e, 'Please try again.')),
                    });
                  },
                },
              ]);
            }, 150);
          },
        },
      ];

      setMenu({ visible: true, title, x, y, width: w, height: h, actions });
    },
    [renameChat, renameDx, deleteChat, deleteDx, dismissMenu, opts],
  );

  return { menu, openMenu, dismissMenu };
}
