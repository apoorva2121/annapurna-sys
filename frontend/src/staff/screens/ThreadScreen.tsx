import { type ReactElement, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import type { MessagePriority } from '@shared/enums';
import { Button } from '@shared/ui/button';
import { useIdempotencyKey } from '@shared/useIdempotencyKey';
import { AttachmentControl } from '@staff/components/AttachmentControl';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { useAuth } from '@staff/auth/AuthContext';
import {
  type Message,
  useCommunicationStream,
  useConversation,
  useDeleteMessage,
  useMarkRead,
  usePromoteMessage,
  useSendMessage,
  useThread,
} from '@staff/api/communication';

/**
 * One conversation: what was said, and the three things that can be done with a message.
 *
 * **Waiter surface in spirit** — a phone, one hand, standing up — so every control is
 * `min-h-target` and the composer is at the bottom where a thumb already is.
 *
 * **Reading is a side effect of arriving**, which is what a watermark makes cheap: the newest
 * message id is sent once when the thread loads, and the server refuses to move it backwards. No
 * per-message receipts, no scroll tracking.
 *
 * **A deleted message renders as a tombstone**, not as a gap. The row, the sender and the moment
 * stay; the words are gone, because a thread that silently loses a line is a thread nobody can
 * rely on in an argument.
 *
 * **Promote is on the message, not on the screen.** The whole reason this module exists rather
 * than a WhatsApp group is that an instruction is one tap from being work with an owner.
 */
export default function ThreadScreen(): ReactElement {
  const { conversationId = '' } = useParams();
  const conversation = useConversation(conversationId);
  const thread = useThread(conversationId);
  const markRead = useMarkRead();
  useCommunicationStream();

  const newest = thread.data?.items[0]?.id;
  useEffect(() => {
    if (newest !== undefined) {
      markRead.mutate({ conversationId, lastReadMessageId: newest });
    }
    // `markRead` is a stable mutation object; including it would re-run this on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, newest]);

  return (
    <div className="flex flex-col gap-page p-page">
      {/* Brand §8.7: a screen reached *into*, with an id in its address, always has a way out
          that is not the browser's Back button. */}
      <Link to="/messages" className="text-sm text-muted-foreground" data-back>
        {strings.messages.backToInbox}
      </Link>
      <h1 className="text-xl font-semibold md:text-2xl">
        {conversation.data?.title ?? strings.messages.noTitle}
      </h1>
      {conversation.data === undefined ? null : (
        <p className="text-sm text-muted-foreground">
          {strings.messages.participants(
            conversation.data.participants.filter((row) => row.left_at === null).length,
          )}
        </p>
      )}

      <QueryState
        isPending={thread.isPending}
        error={thread.error}
        pendingLabel={strings.messages.threadLoading}
      >
        {thread.data === undefined ? null : thread.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{strings.messages.threadEmpty}</p>
        ) : (
          <ul className="flex flex-col-reverse gap-4">
            {thread.data.items.map((message) => (
              <MessageRow
                key={message.id}
                message={message}
                conversationId={conversationId}
              />
            ))}
          </ul>
        )}
      </QueryState>

      <Composer conversationId={conversationId} />
    </div>
  );
}

const PRIORITY_TONE: Record<MessagePriority, string> = {
  normal: '',
  high: 'bg-warning-soft text-warning',
  urgent: 'bg-critical-soft text-critical',
};

/**
 * A tombstone renders as a tombstone.
 *
 * Its own component rather than an early return, because the two are genuinely different rows: a
 * deleted message has no body, no attachments and nothing that can be done with it, and writing
 * them as one function made that function about the difference rather than about a message.
 */
function Tombstone({ message }: { message: Message }): ReactElement {
  return (
    <li className="flex flex-col gap-1 border-b border-border pb-3">
      <span className="text-sm text-muted-foreground">{message.sender_name ?? ''}</span>
      <span className="italic text-muted-foreground">{strings.messages.deleted}</span>
    </li>
  );
}

function MessageRow({
  message,
  conversationId,
}: {
  message: Message;
  conversationId: string;
}): ReactElement {
  const { session } = useAuth();
  const mine = message.sender_employee_id === session?.employeeId;

  if (message.is_deleted) {
    return <Tombstone message={message} />;
  }

  return (
    <li className="flex flex-col gap-2 border-b border-border pb-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{message.sender_name ?? ''}</span>
        {message.priority === 'normal' ? null : (
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${PRIORITY_TONE[message.priority]}`}
          >
            {strings.messages.priority[message.priority]}
          </span>
        )}
      </div>
      <p className="whitespace-pre-wrap">{message.body}</p>

      <AttachmentControl
        ownerType="message"
        ownerId={message.id}
        attachments={message.attachments}
        label={strings.messages.attach}
      />

      <MessageActions message={message} conversationId={conversationId} mine={mine} />
    </li>
  );
}

/**
 * The two things a message can become: a task, or a tombstone.
 *
 * Split out because `MessageRow` was over the complexity budget with it inline — which is the
 * budget doing its job: the row renders what was said, and this renders what can be done about it.
 */
function MessageActions({
  message,
  conversationId,
  mine,
}: {
  message: Message;
  conversationId: string;
  mine: boolean;
}): ReactElement {
  const remove = useDeleteMessage();
  const promote = usePromoteMessage();

  return (
    <>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="ghost"
          disabled={promote.isPending}
          onClick={() => { promote.mutate({ messageId: message.id, priority: 'normal' }); }}
        >
          {promote.isPending ? strings.messages.promoting : strings.messages.promote}
        </Button>
        {mine ? (
          <Button
            variant="ghost"
            disabled={remove.isPending}
            onClick={() => { remove.mutate({ messageId: message.id, conversationId }); }}
          >
            {remove.isPending ? strings.messages.deleting : strings.messages.deleteAction}
          </Button>
        ) : null}
      </div>

      {promote.isSuccess ? <Notice tone="success" title={strings.messages.promoted} /> : null}
      {promote.error === null ? null : <Notice tone="critical" {...errorProps(promote.error)} />}
      {remove.error === null ? null : <Notice tone="critical" {...errorProps(remove.error)} />}
    </>
  );
}

function Composer({ conversationId }: { conversationId: string }): ReactElement {
  const [body, setBody] = useState('');
  const [priority, setPriority] = useState<MessagePriority>('normal');
  const send = useSendMessage();
  const { key, renew } = useIdempotencyKey();

  return (
    <section className="flex flex-col gap-2">
      <label className="sr-only" htmlFor="message-body">
        {strings.messages.composePlaceholder}
      </label>
      <textarea
        id="message-body"
        className="min-h-target rounded-md border border-border bg-background px-3 py-2 text-base"
        rows={2}
        value={body}
        onChange={(event) => { setBody(event.target.value); }}
        placeholder={strings.messages.composePlaceholder}
      />

      <div className="flex flex-wrap gap-2">
        {(['normal', 'high', 'urgent'] as const).map((level) => (
          <Button
            key={level}
            variant={priority === level ? 'primary' : 'secondary'}
            onClick={() => { setPriority(level); }}
          >
            {strings.messages.priority[level]}
          </Button>
        ))}
      </div>

      <Button
        disabled={body.trim() === '' || send.isPending}
        onClick={() => {
          send.mutate(
            { conversationId, body, priority, idempotencyKey: key },
            {
              onSuccess: () => {
                setBody('');
                setPriority('normal');
                renew();
              },
            },
          );
        }}
      >
        {send.isPending ? strings.messages.sending : strings.messages.send}
      </Button>

      {send.error === null ? null : <Notice tone="critical" {...errorProps(send.error)} />}
    </section>
  );
}
