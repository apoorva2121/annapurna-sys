import { type ReactElement, useRef, useState } from 'react';

import { apiGetBlob } from '@shared/api';
import type { AttachmentOwnerType } from '@shared/enums';
import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  ALLOWED_UPLOAD_TYPES,
  MAX_UPLOAD_BYTES,
  type Attachment,
  attachmentHref,
  useUploadAttachment,
} from '@staff/api/communication';

/**
 * Attach a photograph or a PDF to a message, a task or a waste log.
 *
 * **The type and the size are checked here before anything is sent**, mirroring the server's
 * allow-list. Not as a substitute for the server — which reads the stored object's first bytes back
 * and refuses anything that is not what it claimed — but because refusing a 40 MB video after
 * uploading it over a restaurant's connection is a minute of somebody's life for an answer we had
 * at the moment they picked it.
 *
 * **Four states, explicitly** (`docs/engineering-standards.md` §5): choosing, uploading with the
 * button disabled and its label saying so, the failure in place with the server's own words, and
 * **the success named**. The success state was missing until 2026-09-19, and its absence was worse
 * than it sounds: silence after an upload reads as failure, so the natural response is to send the
 * photo again, and again, over a restaurant's connection.
 *
 * **An attachment is fetched, never linked.** This product authenticates with a Bearer token in a
 * header, and a browser following an `<a href>` sends cookies and cannot send one — so every
 * attachment link in the product returned `auth.required` from M11 until 2026-09-19. The bytes are
 * fetched through the normal client, which attaches the token, and handed to the browser as an
 * object URL. A token in the query string would have been the other obvious fix and is refused:
 * a URL travels into history, logs and `Referer` headers, and a live credential must not.
 *
 * **A thumbnail is not rendered**, for the same reason the server sends
 * `Content-Disposition: attachment` and a sandbox CSP: rendering bytes somebody else chose inside
 * this origin's page is exactly what that header exists to prevent. So the object URL is handed to
 * a download, never to an `<img>` or a new tab.
 */
export function AttachmentControl({
  ownerType,
  ownerId,
  attachments,
  onUploaded,
  label,
}: {
  ownerType: AttachmentOwnerType;
  ownerId: string;
  attachments: Attachment[];
  onUploaded?: () => void;
  label?: string;
}): ReactElement {
  const input = useRef<HTMLInputElement>(null);
  const [rejected, setRejected] = useState<string | null>(null);
  const [attached, setAttached] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [openFailed, setOpenFailed] = useState(false);
  const upload = useUploadAttachment();

  /** Fetch the bytes with this session's token, then hand them to the browser as a download. */
  const open = (attachment: Attachment): void => {
    setOpening(attachment.id);
    setOpenFailed(false);
    void apiGetBlob(attachmentHref(attachment.id))
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        // A programmatic download rather than `window.open`: the fetch is asynchronous, so a new
        // tab opened after it is outside the click and every popup blocker stops it. The server
        // sends `Content-Disposition: attachment` anyway — this is the behaviour it asked for.
        const link = document.createElement('a');
        link.href = url;
        link.download = attachment.file_name;
        document.body.append(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      })
      .catch(() => {
        setOpenFailed(true);
      })
      .finally(() => {
        setOpening(null);
      });
  };

  const choose = (file: File | undefined): void => {
    if (file === undefined) {
      return;
    }
    setRejected(null);
    setAttached(null);
    if (!(ALLOWED_UPLOAD_TYPES as readonly string[]).includes(file.type)) {
      setRejected(strings.attachments.rejectedType);
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setRejected(strings.attachments.rejectedSize);
      return;
    }
    upload.mutate(
      { ownerType, ownerId, file },
      {
        onSuccess: () => {
          setAttached(file.name);
          onUploaded?.();
          if (input.current !== null) {
            // Cleared so picking the same file twice fires `change` again — a retry after a
            // failure otherwise does nothing and reads as the button being broken.
            input.current.value = '';
          }
        },
      },
    );
  };

  return (
    <div className="flex flex-col gap-2">
      {attachments.length === 0 ? null : (
        <ul className="flex flex-col gap-1">
          {attachments.map((attachment) => (
            <li key={attachment.id}>
              <button
                type="button"
                className="inline-flex min-h-target items-center underline disabled:opacity-60"
                disabled={opening === attachment.id}
                onClick={() => {
                  open(attachment);
                }}
              >
                {opening === attachment.id
                  ? strings.attachments.opening
                  : attachment.file_name}
              </button>
            </li>
          ))}
        </ul>
      )}

      <input
        ref={input}
        type="file"
        className="sr-only"
        accept={ALLOWED_UPLOAD_TYPES.join(',')}
        onChange={(event) => { choose(event.target.files?.[0]); }}
      />
      <Button
        variant="secondary"
        disabled={upload.isPending}
        onClick={() => { input.current?.click(); }}
      >
        {upload.isPending
          ? strings.attachments.adding
          : (label ?? strings.attachments.add)}
      </Button>
      <p className="text-xs text-muted-foreground">{strings.attachments.allowed}</p>

      {attached === null ? null : (
        <Notice tone="success" title={strings.attachments.attached(attached)} />
      )}
      {openFailed ? <Notice tone="critical" title={strings.attachments.openFailed} /> : null}
      {rejected === null ? null : <Notice tone="critical" title={rejected} />}
      {upload.error === null ? null : <Notice tone="critical" {...errorProps(upload.error)} />}
    </div>
  );
}
