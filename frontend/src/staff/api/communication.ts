import { useEffect, useRef, useState } from 'react';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPutBytes,
  openEventStream,
  putToSignedUrl,
} from '@shared/api';
import type {
  AttachmentOwnerType,
  ConversationType,
  MessagePriority,
  TaskPriority,
  TaskStatus,
} from '@shared/enums';

/**
 * Conversations, messages, tasks and attachments.
 *
 * **The inbox is the source of truth for unread, and the stream only invalidates it.** The server
 * deliberately does not push a count: a number sent down a socket is a second source of truth for
 * something one indexed query already answers, and the two drift the first time an event is
 * dropped or replayed. So a `message` event marks the inbox stale and TanStack refetches it —
 * one request against an index, always right.
 *
 * **An attachment is three calls, and the middle one may not come here at all.** `begin` asks the
 * server where to put the bytes; with a bucket that URL is the bucket's, and the file never passes
 * through our API. `confirm` is what makes it real — the server reads the stored object back and
 * refuses anything that is not what it claimed to be. A screen that skips `confirm` has uploaded
 * nothing.
 *
 * **Sending carries an idempotency key made when the button was pressed** (ADR 0010), for the
 * reason logging waste does: a phone on a bad connection in a kitchen, and a thumb that taps
 * twice.
 */

const COMMS_KEY = ['staff', 'communication'] as const;
const INBOX_KEY = [...COMMS_KEY, 'inbox'] as const;
const TASKS_KEY = [...COMMS_KEY, 'tasks'] as const;

export type Attachment = {
  id: string;
  owner_type: AttachmentOwnerType;
  owner_id: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  status: 'pending' | 'ready';
  uploaded_by: string;
  uploaded_by_name: string | null;
  created_at: string;
};

export type UploadInstruction = {
  method: string;
  url: string;
  /** Sent exactly as given: with a bucket the content type is part of what was signed. */
  headers: Record<string, string>;
  expires_at: string;
};

export type InboxEntry = {
  id: string;
  type: ConversationType;
  title: string | null;
  last_message_at: string | null;
  unread: number;
  has_urgent_unread: boolean;
  is_muted: boolean;
};

export type Participant = {
  employee_id: string;
  full_name: string;
  joined_at: string;
  left_at: string | null;
};

export type Conversation = {
  id: string;
  type: ConversationType;
  title: string | null;
  ref_type: string | null;
  ref_id: string | null;
  created_by: string;
  last_message_at: string | null;
  participants: Participant[];
};

export type Message = {
  id: string;
  conversation_id: string;
  sender_employee_id: string;
  sender_name: string | null;
  body: string | null;
  priority: MessagePriority;
  reply_to_message_id: string | null;
  /** A tombstone renders as a tombstone: the row, the sender, the moment, and no words. */
  is_deleted: boolean;
  attachments: Attachment[];
  created_at: string;
};

export type Task = {
  id: string;
  title: string;
  description: string | null;
  source_message_id: string | null;
  complaint_id: string | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  assigned_by: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  due_at: string | null;
  /** Derived by the server on every read. Nothing flips a flag when a due time passes. */
  is_overdue: boolean;
  completed_at: string | null;
  verified_at: string | null;
  verified_by: string | null;
  attachments: Attachment[];
  created_at: string;
};

export type TaskEvent = {
  id: string;
  actor_employee_id: string;
  actor_name: string | null;
  from_status: TaskStatus | null;
  to_status: TaskStatus | null;
  note: string | null;
  occurred_at: string;
};

// --------------------------------------------------------------------------- conversations

export function useInbox(unreadOnly = false): UseQueryResult<{ items: InboxEntry[] }> {
  return useQuery({
    queryKey: [...INBOX_KEY, unreadOnly],
    queryFn: () =>
      apiGet<{ items: InboxEntry[] }>(`/staff/conversations${unreadOnly ? '?unread_only=true' : ''}`),
  });
}

export function useConversation(conversationId: string): UseQueryResult<Conversation> {
  return useQuery({
    queryKey: [...COMMS_KEY, 'conversation', conversationId],
    queryFn: () => apiGet<Conversation>(`/staff/conversations/${conversationId}`),
  });
}

export function useThread(conversationId: string): UseQueryResult<{ items: Message[] }> {
  return useQuery({
    queryKey: [...COMMS_KEY, 'thread', conversationId],
    queryFn: () => apiGet<{ items: Message[] }>(`/staff/conversations/${conversationId}/messages`),
  });
}

export function useStartConversation(): UseMutationResult<
  Conversation,
  Error,
  { type: ConversationType; title?: string; participantIds: string[] }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ type, title, participantIds }) =>
      apiPost<Conversation>('/staff/conversations', {
        type,
        ...(title === undefined ? {} : { title }),
        participant_ids: participantIds,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: INBOX_KEY });
    },
  });
}

export function useSendMessage(): UseMutationResult<
  Message,
  Error,
  {
    conversationId: string;
    body: string;
    priority: MessagePriority;
    idempotencyKey: string;
  }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, body, priority, idempotencyKey }) =>
      apiPost<Message>(
        '/staff/messages',
        { conversation_id: conversationId, body, priority },
        { idempotencyKey },
      ),
    onSuccess: (message) => {
      void client.invalidateQueries({
        queryKey: [...COMMS_KEY, 'thread', message.conversation_id],
      });
      void client.invalidateQueries({ queryKey: INBOX_KEY });
    },
  });
}

export function useDeleteMessage(): UseMutationResult<
  Message,
  Error,
  { messageId: string; conversationId: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId }) => apiDelete<Message>(`/staff/messages/${messageId}`),
    onSuccess: (_message, { conversationId }) => {
      void client.invalidateQueries({ queryKey: [...COMMS_KEY, 'thread', conversationId] });
    },
  });
}

export function useMarkRead(): UseMutationResult<
  void,
  Error,
  { conversationId: string; lastReadMessageId: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ conversationId, lastReadMessageId }) => {
      await apiPatch<undefined>(`/staff/conversations/${conversationId}/read`, {
        last_read_message_id: lastReadMessageId,
      });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: INBOX_KEY });
    },
  });
}

// ---------------------------------------------------------------------------------- tasks

export function useTasks(mineOnly = false): UseQueryResult<{ items: Task[] }> {
  return useQuery({
    queryKey: [...TASKS_KEY, mineOnly],
    queryFn: () => apiGet<{ items: Task[] }>(`/staff/tasks${mineOnly ? '?mine_only=true' : ''}`),
  });
}

export function useTask(taskId: string): UseQueryResult<{ task: Task; events: TaskEvent[] }> {
  return useQuery({
    queryKey: [...TASKS_KEY, 'detail', taskId],
    queryFn: () => apiGet<{ task: Task; events: TaskEvent[] }>(`/staff/tasks/${taskId}`),
  });
}

export function useCreateTask(): UseMutationResult<
  Task,
  Error,
  {
    title: string;
    description?: string;
    assignedTo?: string | null;
    priority: TaskPriority;
    dueAt?: string | null;
  }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ title, description, assignedTo, priority, dueAt }) =>
      apiPost<Task>('/staff/tasks', {
        title,
        ...(description === undefined ? {} : { description }),
        ...(assignedTo === undefined || assignedTo === null ? {} : { assigned_to: assignedTo }),
        priority,
        ...(dueAt === undefined || dueAt === null ? {} : { due_at: dueAt }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: TASKS_KEY });
    },
  });
}

export function useMoveTask(): UseMutationResult<
  Task,
  Error,
  { taskId: string; status: TaskStatus; note?: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, status, note }) =>
      apiPost<Task>(`/staff/tasks/${taskId}/status`, {
        status,
        ...(note === undefined || note === '' ? {} : { note }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: TASKS_KEY });
    },
  });
}

export function useAssignTask(): UseMutationResult<
  Task,
  Error,
  { taskId: string; assignedTo: string | null; note?: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, assignedTo, note }) =>
      apiPost<Task>(`/staff/tasks/${taskId}/assign`, {
        assigned_to: assignedTo,
        ...(note === undefined || note === '' ? {} : { note }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: TASKS_KEY });
    },
  });
}

export function usePromoteMessage(): UseMutationResult<
  Task,
  Error,
  { messageId: string; title?: string; assignedTo?: string | null; priority: TaskPriority }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, title, assignedTo, priority }) =>
      apiPost<Task>(`/staff/messages/${messageId}/promote`, {
        ...(title === undefined ? {} : { title }),
        ...(assignedTo === undefined || assignedTo === null ? {} : { assigned_to: assignedTo }),
        priority,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: TASKS_KEY });
    },
  });
}

// ---------------------------------------------------------------------------- attachments

/** The allow-list, mirrored from `app/core/media.py` so a file is refused before it is uploaded. */
export const ALLOWED_UPLOAD_TYPES = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'application/pdf',
] as const;

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export type AttachmentTarget = { ownerType: AttachmentOwnerType; ownerId: string };

/**
 * Begin, put, confirm — in that order, and all three or none.
 *
 * The middle step may not reach this API at all: with a bucket the instruction points at the
 * bucket, and the bytes go straight there. That is why the upload uses `fetch` with the returned
 * method, URL and headers rather than one of the `api*` helpers, which would attach our own
 * `Authorization` header to somebody else's host.
 */
export function useUploadAttachment(): UseMutationResult<
  Attachment,
  Error,
  AttachmentTarget & { file: File }
> {
  return useMutation({
    mutationFn: async ({ ownerType, ownerId, file }) => {
      const begun = await apiPost<{ attachment: Attachment; upload: UploadInstruction }>(
        '/staff/attachments',
        {
          owner_type: ownerType,
          owner_id: ownerId,
          file_name: file.name,
          mime_type: file.type,
          size_bytes: file.size,
        },
      );
      // **Where the bytes go decides whether our token goes with them.** A relative URL is this
      // API's own upload route and needs the session's bearer token; an absolute one is a bucket,
      // already signed, and attaching our token there would hand a credential to another host.
      if (begun.upload.url.startsWith('/')) {
        await apiPutBytes(
          begun.upload.url.replace('/api/v1', ''),
          file,
          begun.upload.headers['Content-Type'] ?? file.type,
        );
      } else {
        await putToSignedUrl(
          begun.upload.url,
          begun.upload.method,
          begun.upload.headers,
          file,
        );
      }
      return apiPost<Attachment>(`/staff/attachments/${begun.attachment.id}/confirm`);
    },
  });
}

/** Where to fetch an attachment. The server redirects to a signed URL, or serves the bytes. */
export function attachmentHref(attachmentId: string): string {
  return `/api/v1/staff/attachments/${attachmentId}`;
}

// --------------------------------------------------------------------------------- stream

export type StreamState = 'connecting' | 'live' | 'reconnecting';

/**
 * New messages and task changes, as they happen.
 *
 * `useKitchenStream`'s shape, with one deliberate difference: an event here **invalidates** rather
 * than writing into the cache. The kitchen display replaces a whole ticket by id because a chef
 * must see a change within a second; an inbox can afford one refetch, and refetching is what keeps
 * the unread count a query rather than a number two places could disagree about.
 */
export function useCommunicationStream(): StreamState {
  const client = useQueryClient();
  const [state, setState] = useState<StreamState>('connecting');
  const cursor = useRef<string | null>(null);
  const backoff = useRef(5000);

  useEffect(() => {
    const controller = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = async (): Promise<void> => {
      try {
        await openEventStream('/staff/messages/stream', {
          signal: controller.signal,
          lastEventId: cursor.current,
          onRetryInterval: (milliseconds) => {
            backoff.current = milliseconds;
          },
          onEvent: (event) => {
            setState('live');
            applyEvent(client, event.event);
            if (event.id !== null) {
              cursor.current = event.id;
            }
          },
        });
      } catch {
        // Every failure is the same failure to somebody reading their messages: not live. The
        // banner says so and the connection is retried.
      }
      if (!stopped) {
        setState('reconnecting');
        timer = setTimeout(() => void connect(), backoff.current);
      }
    };

    void connect();
    return () => {
      stopped = true;
      controller.abort();
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [client]);

  return state;
}

function applyEvent(client: QueryClient, kind: string): void {
  if (kind === 'message') {
    void client.invalidateQueries({ queryKey: INBOX_KEY });
    void client.invalidateQueries({ queryKey: [...COMMS_KEY, 'thread'] });
    return;
  }
  if (kind === 'task') {
    void client.invalidateQueries({ queryKey: TASKS_KEY });
  }
}
