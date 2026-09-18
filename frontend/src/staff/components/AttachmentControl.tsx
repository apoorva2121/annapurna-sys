import { type ReactElement, useRef, useState } from 'react';

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
 * **Three states, explicitly** (`docs/engineering-standards.md` §5): choosing, uploading with the
 * button disabled and its label saying so, and the failure in place with the server's own words.
 *
 * **A thumbnail is not rendered.** An attachment is a link with its filename, because rendering an
 * uploaded image inline would put bytes somebody else chose inside this origin's page, which is
 * exactly what `Content-Disposition: attachment` on the download route exists to prevent.
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
  const upload = useUploadAttachment();

  const choose = (file: File | undefined): void => {
    if (file === undefined) {
      return;
    }
    setRejected(null);
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
              <a
                className="inline-flex min-h-target items-center underline"
                href={attachmentHref(attachment.id)}
                target="_blank"
                rel="noreferrer"
              >
                {attachment.file_name}
              </a>
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

      {rejected === null ? null : <Notice tone="critical" title={rejected} />}
      {upload.error === null ? null : <Notice tone="critical" {...errorProps(upload.error)} />}
    </div>
  );
}
