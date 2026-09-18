"""Uploading a file, checking it is what it claims to be, and serving it back.

The module's one genuinely new subsystem, and the one worth reading carefully.

**Three steps, because with a presigned upload the bytes never pass through this process.** `begin`
issues a key and an instruction; the client PUTs the bytes (at the bucket, or at this API when the
driver cannot sign); `confirm` asks *the store* how big the object is and reads its first bytes
back. Validation cannot live in an upload handler, because under the S3 driver there is no upload
handler. That it has to work this way is a gift: the filesystem driver runs the same three steps,
so the sniffing test exercises the real path rather than a second implementation of it.

**You may attach to what you may write.** One table, six owner types, and no permission per type —
that would be six permissions that drift apart. The route declares `message.send`, which every role
holds and which means only "may use the attachment mechanism"; the question that decides the matter
is asked here, against the owner object, loaded through its own repository so that tenant scope
comes free and another restaurant's `owner_id` is a 404 before any file exists.

**A refused upload takes its object with it.** A `.jpg` whose first two bytes are `MZ` does not
leave a row behind for somebody to wonder about, and does not leave an object behind to pay for.

**Nothing here logs a file name or a key.** A filename is user input and an attachment on a
complaint can be named anything at all.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import media
from app.core.actor import Actor
from app.core.config import get_settings
from app.core.enums import AttachmentOwnerType, AttachmentStatus
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.ids import uuid7
from app.core.permissions import PermissionCode
from app.core.tenancy import TenantScope
from app.models.communication import Attachment
from app.repositories.communication import (
    AttachmentRepository,
    ConversationRepository,
    MessageRepository,
    TaskRepository,
)
from app.repositories.customers import ComplaintRepository, FeedbackRepository
from app.repositories.procurement import GoodsReceiptRepository
from app.repositories.waste import WastageEventRepository
from app.storage.port import StoragePort, UploadInstruction

logger = logging.getLogger(__name__)

# How long a begun-but-unconfirmed upload may sit before the sweep takes it. An hour is far longer
# than any upload and far shorter than a bill anybody would notice.
PENDING_LIFETIME = timedelta(hours=1)

# Where this API's staff routes live. Written once here rather than assembled in three places,
# because the first version of this got it wrong by a path segment and the symptom was a 404 on an
# upload URL the server itself had just handed out.
STAFF_PREFIX = "/api/v1/staff"


@dataclass(frozen=True, slots=True)
class BegunUpload:
    attachment: Attachment
    instruction: UploadInstruction


@dataclass(frozen=True, slots=True)
class Download:
    """Either a URL to redirect to, or bytes to serve. Never both, and never neither."""

    url: str | None
    content: bytes | None
    file_name: str
    mime_type: str


class AttachmentService:
    def __init__(self, session: AsyncSession, scope: TenantScope, storage: StoragePort) -> None:
        self.session = session
        self.scope = scope
        self.storage = storage
        self._attachments = AttachmentRepository(session, scope)
        self._messages = MessageRepository(session, scope)
        self._conversations = ConversationRepository(session, scope)
        self._tasks = TaskRepository(session, scope)
        self._wastage = WastageEventRepository(session, scope)
        self._complaints = ComplaintRepository(session, scope)
        self._feedback = FeedbackRepository(session, scope)
        self._receipts = GoodsReceiptRepository(session, scope)

    # ------------------------------------------------------------------ writing

    async def begin(
        self,
        actor: Actor,
        *,
        owner_type: AttachmentOwnerType,
        owner_id: uuid.UUID,
        file_name: str,
        mime_type: str,
        size_bytes: int,
    ) -> BegunUpload:
        settings = get_settings()
        if not media.is_allowed(mime_type):
            raise AppError(
                "attachment.type_not_allowed",
                "That kind of file cannot be attached. Photographs and PDFs only.",
                details={"allowed": sorted(media.ALLOWED_CONTENT_TYPES)},
                status_code=422,
            )
        if size_bytes <= 0 or size_bytes > settings.storage_max_bytes:
            raise AppError(
                "attachment.too_large",
                f"That file is too large. The limit is "
                f"{settings.storage_max_bytes // (1024 * 1024)} MB.",
                status_code=422,
            )
        await self._authorise_write(actor, owner_type, owner_id)

        attachment_id = uuid7()
        attachment = Attachment(
            id=attachment_id,
            restaurant_id=self.scope.restaurant_id,
            owner_type=owner_type.value,
            owner_id=owner_id,
            file_key=self._key(attachment_id, mime_type),
            file_name=media.safe_file_name(file_name),
            mime_type=mime_type,
            size_bytes=size_bytes,
            uploaded_by=self._employee_id(actor),
            status=AttachmentStatus.PENDING.value,
        )
        self.session.add(attachment)
        await self.session.flush()

        if self.storage.presigns_uploads:
            instruction = await self.storage.presigned_put(
                attachment.file_key, content_type=mime_type, size_bytes=size_bytes
            )
        else:
            # Nothing to sign, so the bytes come through this API. The URL is built from the route
            # rather than from the store, which is the one thing the layers above are allowed to
            # know about the driver.
            instruction = UploadInstruction(
                method="PUT",
                url=f"{STAFF_PREFIX}/attachments/{attachment.id}/content",
                headers={"Content-Type": mime_type},
                expires_at=datetime.now(UTC) + PENDING_LIFETIME,
            )
        return BegunUpload(attachment=attachment, instruction=instruction)

    async def store_content(self, actor: Actor, attachment_id: uuid.UUID, data: bytes) -> None:
        """The upload route for a driver that cannot presign. Refuses anything already confirmed —
        otherwise a checked object could be replaced by an unchecked one under the same id."""
        attachment = await self._own_pending(actor, attachment_id)
        settings = get_settings()
        if len(data) > settings.storage_max_bytes:
            raise AppError(
                "attachment.too_large",
                f"That file is too large. The limit is "
                f"{settings.storage_max_bytes // (1024 * 1024)} MB.",
                status_code=422,
            )
        await self.storage.write(attachment.file_key, data, content_type=str(attachment.mime_type))

    async def confirm(self, actor: Actor, attachment_id: uuid.UUID) -> Attachment:
        """Ask the store what is actually there, and refuse it if it is not what was claimed."""
        attachment = await self._own_pending(actor, attachment_id)
        settings = get_settings()

        facts = await self.storage.facts(attachment.file_key)
        if facts is None:
            raise AppError(
                "attachment.not_uploaded",
                "The file did not finish uploading. Try attaching it again.",
                status_code=409,
            )
        if facts.size_bytes > settings.storage_max_bytes or facts.size_bytes != int(
            attachment.size_bytes
        ):
            # The declared size is a client's claim and a presigned PUT is not bound to it in every
            # S3 implementation, so the store's answer is the one that counts.
            await self._discard(attachment)
            raise AppError(
                "attachment.size_mismatch",
                "The uploaded file was not the size it said it was, so it was discarded.",
                status_code=422,
            )

        head = await self.storage.read(attachment.file_key, media.SIGNATURE_BYTES)
        if not media.matches_signature(str(attachment.mime_type), head):
            await self._discard(attachment)
            logger.warning(
                "attachment.signature_rejected",
                extra={
                    "restaurant_id": str(self.scope.restaurant_id),
                    "attachment_id": str(attachment.id),
                    "declared_type": attachment.mime_type,
                },
            )
            raise AppError(
                "attachment.content_mismatch",
                "That file is not the kind of file it claims to be, so it was discarded.",
                status_code=422,
            )

        attachment.status = AttachmentStatus.READY.value
        attachment.size_bytes = facts.size_bytes
        await self.session.flush()
        return attachment

    async def remove(self, actor: Actor, attachment_id: uuid.UUID) -> None:
        attachment = await self._get(attachment_id)
        await self._authorise_write(
            actor, AttachmentOwnerType(attachment.owner_type), attachment.owner_id
        )
        await self._discard(attachment)

    # ------------------------------------------------------------------ reading

    async def download(self, actor: Actor, attachment_id: uuid.UUID) -> Download:
        attachment = await self._get(attachment_id)
        if attachment.status != AttachmentStatus.READY.value:
            raise NotFoundError("attachment.not_found", "That attachment is not available.")
        await self._authorise_read(
            actor, AttachmentOwnerType(attachment.owner_type), attachment.owner_id
        )
        url = await self.storage.download_url(
            attachment.file_key, file_name=str(attachment.file_name)
        )
        content = None if url is not None else await self.storage.read(attachment.file_key)
        return Download(
            url=url,
            content=content,
            file_name=str(attachment.file_name),
            mime_type=str(attachment.mime_type),
        )

    async def sweep(self, *, now: datetime | None = None) -> int:
        """Delete objects and rows for uploads that were begun and abandoned.

        Without it a bucket fills with orphans that no row references, no screen shows and no
        erasure reaches.
        """
        moment = now or datetime.now(UTC)
        stale = await self._attachments.stale_pending(older_than=moment - PENDING_LIFETIME)
        for attachment in stale:
            await self.storage.delete(str(attachment.file_key))
            await self.session.delete(attachment)
        await self.session.flush()
        return len(stale)

    # ------------------------------------------------------------------ internals

    def _key(self, attachment_id: uuid.UUID, mime_type: str) -> str:
        """`{restaurant}/{yyyy}/{mm}/{uuid7}{ext}`.

        The tenant is in the key so a mis-scoped bucket policy is still tenant-shaped; the date
        prefix keeps a listing usable; the uuid means an uploaded `../../etc/passwd` is a display
        name and nothing else.
        """
        moment = datetime.now(UTC)
        return (
            f"{self.scope.restaurant_id}/{moment:%Y}/{moment:%m}/"
            f"{attachment_id.hex}{media.extension_for(mime_type)}"
        )

    def _employee_id(self, actor: Actor) -> uuid.UUID:
        """Named rather than inlined: every use of it here means *the person asking*."""
        return actor.employee_id

    async def _get(self, attachment_id: uuid.UUID) -> Attachment:
        attachment = await self._attachments.get(attachment_id)
        if attachment is None:
            raise NotFoundError("attachment.not_found", "That attachment could not be found.")
        return attachment

    async def _own_pending(self, actor: Actor, attachment_id: uuid.UUID) -> Attachment:
        attachment = await self._get(attachment_id)
        if attachment.status != AttachmentStatus.PENDING.value:
            raise AppError(
                "attachment.already_confirmed",
                "That file has already been uploaded.",
                status_code=409,
            )
        if attachment.uploaded_by != self._employee_id(actor):
            # Only the person who began an upload may finish it. Otherwise one person's pending
            # row is another person's way to put bytes under an id somebody else will attach.
            raise PermissionDeniedError(
                "attachment.not_yours", "Only the person who started an upload can finish it."
            )
        return attachment

    async def _discard(self, attachment: Attachment) -> None:
        await self.storage.delete(str(attachment.file_key))
        await self.session.delete(attachment)
        await self.session.flush()

    async def _authorise_write(
        self, actor: Actor, owner_type: AttachmentOwnerType, owner_id: uuid.UUID
    ) -> None:
        """May this actor write the thing being attached to?

        Every branch loads the owner through its own repository, so a cross-tenant id is a 404
        before a key is issued and before any file exists.
        """
        employee_id = self._employee_id(actor)

        if owner_type is AttachmentOwnerType.MESSAGE:
            message = await self._messages.get(owner_id)
            if message is None:
                raise self._no_owner()
            if message.sender_employee_id != employee_id or message.deleted_at is not None:
                raise PermissionDeniedError(
                    "attachment.not_your_message",
                    "You can only attach a file to a message you sent.",
                )
            return

        if owner_type is AttachmentOwnerType.TASK:
            task = await self._tasks.get(owner_id)
            if task is None:
                raise self._no_owner()
            if task.assigned_to != employee_id and not actor.holds(PermissionCode.TASK_ASSIGN):
                raise PermissionDeniedError(
                    "attachment.not_your_task",
                    "You can only attach a file to a task assigned to you.",
                )
            return

        if owner_type is AttachmentOwnerType.WASTAGE_EVENT:
            event = await self._wastage.get(owner_id)
            if event is None:
                raise self._no_owner()
            if event.reported_by != employee_id and not actor.holds(PermissionCode.WASTAGE_APPROVE):
                raise PermissionDeniedError(
                    "attachment.not_your_wastage",
                    "You can only attach a photograph to waste you logged.",
                )
            return

        if owner_type in (AttachmentOwnerType.COMPLAINT, AttachmentOwnerType.FEEDBACK):
            owner = (
                await self._complaints.get(owner_id)
                if owner_type is AttachmentOwnerType.COMPLAINT
                else await self._feedback.get(owner_id)
            )
            if owner is None:
                raise self._no_owner()
            self._require(actor, PermissionCode.COMPLAINT_MANAGE)
            return

        receipt = await self._receipts.get(owner_id)
        if receipt is None:
            raise self._no_owner()
        self._require(actor, PermissionCode.PURCHASE_MANAGE)

    async def _authorise_read(
        self, actor: Actor, owner_type: AttachmentOwnerType, owner_id: uuid.UUID
    ) -> None:
        """Reading is wider than writing, and participation is what widens it.

        A photograph in a thread is visible to everybody in that thread, not only to whoever took
        it — otherwise attaching one would be pointless.
        """
        employee_id = self._employee_id(actor)

        if owner_type is AttachmentOwnerType.MESSAGE:
            message = await self._messages.get(owner_id)
            if message is None:
                raise self._no_owner()
            if await self._conversations.get_for(message.conversation_id, employee_id) is None:
                raise PermissionDeniedError(
                    "attachment.not_in_conversation",
                    "That file is in a conversation you are not part of.",
                )
            return

        if owner_type is AttachmentOwnerType.TASK:
            task = await self._tasks.get(owner_id)
            if task is None:
                raise self._no_owner()
            if (
                task.assigned_to != employee_id
                and task.assigned_by != employee_id
                and not actor.holds(PermissionCode.TASK_ASSIGN)
            ):
                raise PermissionDeniedError(
                    "attachment.not_your_task", "That file belongs to somebody else's task."
                )
            return

        if owner_type is AttachmentOwnerType.WASTAGE_EVENT:
            if await self._wastage.get(owner_id) is None:
                raise self._no_owner()
            self._require(actor, PermissionCode.STOCK_VIEW)
            return

        if owner_type in (AttachmentOwnerType.COMPLAINT, AttachmentOwnerType.FEEDBACK):
            owner = (
                await self._complaints.get(owner_id)
                if owner_type is AttachmentOwnerType.COMPLAINT
                else await self._feedback.get(owner_id)
            )
            if owner is None:
                raise self._no_owner()
            self._require(actor, PermissionCode.FEEDBACK_VIEW)
            return

        if await self._receipts.get(owner_id) is None:
            raise self._no_owner()
        self._require(actor, PermissionCode.SUPPLIER_VIEW)

    def _require(self, actor: Actor, permission: PermissionCode) -> None:
        if not actor.holds(permission):
            raise PermissionDeniedError(
                "attachment.not_permitted", "You do not have permission to do that."
            )

    def _no_owner(self) -> NotFoundError:
        """One message for "no such thing" and "another restaurant's thing", on purpose: telling
        the two apart is how somebody enumerates what exists in a tenant they cannot read."""
        return NotFoundError(
            "attachment.owner_not_found", "The thing you are attaching to could not be found."
        )
