import type { Attachment } from '@/hooks/useAttachMenu';

/** Simple module-level bucket to pass the initial message from the composer to the chat screen. */
let pending: { text: string; files?: Attachment[] } | null = null;

export function setPendingSend(text: string, files?: Attachment[]) {
  pending = { text, files };
}

export function consumePendingSend() {
  const data = pending;
  pending = null;
  return data;
}
