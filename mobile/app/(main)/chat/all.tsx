import { SessionListScreen } from '@/components/SessionListScreen';
import { useChatConversations } from '@/hooks/useChat';

export default function AllChatsScreen() {
  return (
    <SessionListScreen
      config={{
        type: 'chat',
        screenTitle: 'Chats',
        emptyIcon: 'chat-bubbles',
        emptyText: 'No conversations yet',
        emptyAction: 'Start a conversation',
        useData: useChatConversations,
        getTitle: (c) => c.topic || 'New conversation',
        getId: (c) => c.id,
        getRoute: () => '/(main)/chat/[cid]',
        paramName: 'cid',
      }}
    />
  );
}
