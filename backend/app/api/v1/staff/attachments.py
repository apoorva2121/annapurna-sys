"""Attachments. Three steps to upload one, and one route to read it back.

**Every route declares `message.send`, and that is not laziness.** The P1 design has no
`attachment.manage`, and inventing one would have meant either six permissions that drift apart or
one that lets a waiter attach a file to a goods receipt. So the declared permission means "may use
the attachment mechanism at all" — which every role holds — and the question that decides the
matter is asked in the service, against the owner object: *may this actor write this thing?*

**`GET /attachments/{id}` never renders.** With a bucket it redirects to a short-lived signed URL
on the bucket's own host, which is the separate-origin defence `docs/modules.md` asks for. With the
filesystem driver there is no other origin, so the defence is replaced in kind and stated as such:
`Content-Disposition: attachment` always, `X-Content-Type-Options: nosniff`, and a
`Content-Security-Policy: sandbox`. Together with the allow-list — which contains no markup and no
executable type — that is what stops an upload becoming stored XSS against every logged-in session.

**Every write route commits; the service only flushes.** This codebase's convention, and the one
M08 broke after `inventory.py` had documented the symptom in full.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.enums import AttachmentOwnerType, AttachmentStatus
from app.core.errors import AppError
from app.core.permissions import PermissionCode
from app.models.communication import Attachment
from app.schemas.communication import (
    AttachmentBeginRequest,
    AttachmentBegunResponse,
    AttachmentResponse,
    UploadInstructionResponse,
)
from app.services.attachments import AttachmentService
from app.storage import get_storage
from app.storage.port import UploadInstruction

router = APIRouter(tags=["attachments"])

_ATTACH = Annotated[Actor, Depends(require_permission(PermissionCode.MESSAGE_SEND))]

# Read in one go rather than streamed. The cap is 10 MB and the alternative — a streaming body with
# no declared length — is how a size limit becomes advisory.
_MAX_INLINE_UPLOAD = 16 * 1024 * 1024


def _service(session: SessionDep, actor: Actor) -> AttachmentService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return AttachmentService(session, actor.scope, get_storage())


def attachment_response(
    attachment: Attachment, *, uploaded_by_name: str | None = None
) -> AttachmentResponse:
    return AttachmentResponse(
        id=attachment.id,
        owner_type=AttachmentOwnerType(attachment.owner_type),
        owner_id=attachment.owner_id,
        file_name=str(attachment.file_name),
        mime_type=str(attachment.mime_type),
        size_bytes=int(attachment.size_bytes),
        status=AttachmentStatus(attachment.status),
        uploaded_by=attachment.uploaded_by,
        uploaded_by_name=uploaded_by_name,
        created_at=attachment.created_at,
    )


def _instruction(instruction: UploadInstruction) -> UploadInstructionResponse:
    return UploadInstructionResponse(
        method=instruction.method,
        url=instruction.url,
        headers=dict(instruction.headers),
        expires_at=instruction.expires_at,
    )


@router.post(
    "/attachments",
    response_model=AttachmentBegunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def begin_attachment(
    payload: AttachmentBeginRequest, session: SessionDep, actor: _ATTACH
) -> AttachmentBegunResponse:
    """Issue a key and say where to put the bytes.

    The row exists before the file does, and is `pending` until something checks it. A row that is
    still pending an hour later is swept along with anything behind it.
    """
    service = _service(session, actor)
    begun = await service.begin(
        actor,
        owner_type=payload.owner_type,
        owner_id=payload.owner_id,
        file_name=payload.file_name,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
    )
    response = AttachmentBegunResponse(
        attachment=attachment_response(begun.attachment),
        upload=_instruction(begun.instruction),
    )
    await session.commit()
    return response


@router.put("/attachments/{attachment_id}/content", status_code=status.HTTP_204_NO_CONTENT)
async def upload_content(
    attachment_id: uuid.UUID, request: Request, session: SessionDep, actor: _ATTACH
) -> Response:
    """The upload path for a driver that cannot presign.

    With the S3 driver this route is never called — the client PUTs at the bucket — and that is the
    only difference the application above the port is allowed to see.
    """
    body = await request.body()
    if len(body) > _MAX_INLINE_UPLOAD:
        raise AppError("attachment.too_large", "That file is too large to upload.", status_code=413)
    service = _service(session, actor)
    await service.store_content(actor, attachment_id, body)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/attachments/{attachment_id}/confirm", response_model=AttachmentResponse)
async def confirm_attachment(
    attachment_id: uuid.UUID, session: SessionDep, actor: _ATTACH
) -> AttachmentResponse:
    """Ask the store what is actually there, and refuse it if it is not what was claimed.

    A refusal takes the object with it: a `.jpg` whose first bytes are `MZ` leaves no row for
    somebody to wonder about and no object to pay for.
    """
    service = _service(session, actor)
    try:
        attachment = await service.confirm(actor, attachment_id)
    except AppError:
        # **The refusal is a write, and it has to survive the error.** `confirm` deletes the row
        # and the object before raising, and the error handler rolls the request's transaction
        # back — so without this commit a rejected upload leaves its row behind and takes only the
        # object, which is the worst of both. Found by the test that asserts the row is gone; the
        # same shape of bug as M08's vanishing writes, one layer up.
        await session.commit()
        raise
    response = attachment_response(attachment)
    await session.commit()
    return response


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: uuid.UUID, session: SessionDep, actor: _ATTACH
) -> Response:
    """A redirect to the bucket, or the bytes with the headers that replace a separate origin."""
    service = _service(session, actor)
    download = await service.download(actor, attachment_id)
    if download.url is not None:
        return RedirectResponse(download.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    assert download.content is not None  # noqa: S101 - the service returns one or the other
    return Response(
        content=download.content,
        media_type=download.mime_type,
        headers={
            # Saved, never rendered. The three together are what a separate origin would have
            # given us for free.
            "Content-Disposition": f'attachment; filename="{download.file_name}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: uuid.UUID, session: SessionDep, actor: _ATTACH
) -> Response:
    service = _service(session, actor)
    await service.remove(actor, attachment_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
