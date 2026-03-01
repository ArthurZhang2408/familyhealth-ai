import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi } from '@/services/api';
import type { Attachment } from '@/hooks/useAttachMenu';

export function useChatConversations(pid: string) {
  return useQuery({
    queryKey: ['chat', pid],
    queryFn: () => chatApi.list(pid),
    enabled: !!pid,
  });
}

export function useChatConversation(pid: string, cid: string) {
  return useQuery({
    queryKey: ['chat', pid, cid],
    queryFn: () => chatApi.get(pid, cid),
    enabled: !!pid && !!cid,
  });
}

export function useSendChatMessage(pid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      content,
      conversation_id,
      topic,
      files,
    }: {
      content: string;
      conversation_id?: string;
      topic?: string;
      files?: Attachment[];
    }) => chatApi.send(pid, content, conversation_id, topic, files),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['chat', pid] });
      if (variables.conversation_id) {
        qc.invalidateQueries({ queryKey: ['chat', pid, variables.conversation_id] });
      }
    },
  });
}
