# M11 · Communication & Tasks — Module Spec

**Depends on** M01 (employees, roles, sessions). Touches M08 (the stream it generalises), M09
(`requires_photo`, which has been waiting for this module) and M10 (complaint threads).
**Status** — spec written 2026-09-18, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m11-build-log.md`.

Tables: `conversation`, `conversation_participant`, `message`, `task`, `task_event`, `attachment`.
Endpoints: conversations, messages, the message stream, tasks and their events, attachments.
Screens: inbox, thread, task board, task detail, and the attachment control the other three share.

**Three owner decisions were taken before this spec was written** (2026-09-18):

1. **Attachments get a storage port with two drivers** — filesystem and S3 — so nothing in this
   module waits on a bucket existing.
2. **Messages arrive over SSE**, by generalising M08's cursor-poll stream rather than writing a
   second one.
3. **M09's `requires_photo` becomes a nudge, not a block.** The screen asks; the log still saves.

---

## Why this module exists

Every restaurant this product is for already has a communication system. It is a WhatsApp group,
and it works — which is exactly the problem. It works well enough that nobody will migrate to
something merely equivalent, and everything in it is invisible to the rest of the business: the
message that says "AC repair guy coming at 4" is not a task, the photo of a broken fridge is not
attached to anything, and the instruction to 86 the paneer reaches whoever happens to look at their
phone.

So this module is not "chat". Chat is table stakes and we will lose that comparison. What this
module has that WhatsApp cannot have is that **a message is one click from becoming a task with an
owner, a due time and a lifecycle nobody can quietly erase** — and that the task knows which
complaint, which order, which shift it came from.

That is also the honest scope boundary. If a restaurant uses this for gossip, fine; if it uses it
only to turn instructions into tracked work, the module has done its job. The screens are built for
the second thing.

**It is also the fill-week module** (`docs/sdlc.md`, risk table: "M11/M12/M14 are low-intensity
fill weeks"). It follows M07's seven days and M10's guest surface. Nothing in it is novel except
the storage port, which is the one part that deserves care.

---

## Research — what binds this module, checked 2026-09-18

**`docs/compliance-rules.md`: no rule in §A or §B binds staff-to-staff communication.** Checked
rather than assumed, as CLAUDE.md requires. This module touches no menu text, no restaurant
identity, no tax, no price a guest pays. The finding is "no rule applies", and that is a result.

**One DPDP interaction is real and must be written down rather than discovered later.** §B2 (not
in force; Phase 3 commences **13 May 2027**) is the standard M10 built to. M10's erasure anonymises
a customer and keeps the order. A free-text message body and an uploaded file are outside that
sweep: nothing stops a manager typing a guest's phone number into a thread, and erasure will not
find it there.

This module does not solve that, and must not pretend to. What it does instead:

- **A complaint thread references the complaint, never a copy of the customer.** `conversation.
  ref_type='complaint'` + `ref_id`; the customer's name and number are read through the complaint
  at render time, so erasure reaches them.
- **Message bodies are never logged.** The observability rule already says no PII in logs; here it
  hardens to "no message body at any level, ever" — a body is unstructured and therefore
  unclassifiable, so the only safe assumption is that it contains everything.
- **No full-text search index in month 1.** A search index is a second copy of every body, outside
  the erasure sweep and outside the retention story, and nobody asked for it.
- The residual gap goes in `docs/compliance-rules.md` §D as a named gap owned by M16, with its
  trigger: it is closed when a retention policy exists, not before.

**ADR 0005** names S3-compatible object storage and pre-signed media URLs, "never constructed from
a provider-specific host". That is the constraint the storage port is built to satisfy, and the
reason the filesystem driver is an *adapter* rather than a shortcut.

**ADR 0008** makes `message.deleted_at` the schema's one soft-delete exception. It is already
written down; this module is where it becomes code.

**ADR 0009** (guest surface separation) is not engaged: **this module has no guest surface at
all**. No route under `/guest`, no guest token accepted anywhere in it. Stated because a
communication module is exactly where someone would later be tempted to let a guest message the
restaurant, and that would be a new ADR, not an afternoon.

---

## The decisions that matter

### 1 · Everyone talks, including the cleaner

`cleaner` holds **zero** permissions today. A communication module that a cleaner cannot use is a
communication module the restaurant will not adopt, because the person who finds the broken freezer
at 6am is exactly the person with no permissions.

So `message.send`, `task.view` and `task.complete` are granted to **every role in the
catalogue**, and the module's tests assert that over the catalogue — the same mechanism M17 uses
for `performance.view.own` ("granted to every role and not removable"). A role added later fails
the test rather than silently losing access.

This is not a weakening of access control. It is the recognition that the permission that matters
here is **participation**, not role: you see a conversation because you are a participant in it,
and the repository scope enforces that on every read. A permission catalogue cannot express "this
thread, not that one"; a participant row can.

**This module invents no permission code.** The P1 design in `seed/organization.yaml` — written
in P1 and guarded by `test_the_shipped_catalogue_is_a_subset_of_the_p1_design` — already contains
exactly four comms codes and already grants three of them to every role, cleaner included. The
design got here first and it was right. Four codes, not the seven a fresh reading would have
invented:

| Permission | Who holds it | What it means here |
|---|---|---|
| `message.send` | **every role** | take part in conversations at all: read the threads you are a participant of, post, attach a file |
| `task.view` | **every role** | see tasks assigned to you, and write down your own work |
| `task.complete` | **every role** | move a task you were assigned along its lifecycle |
| `task.assign` | owner, manager | give work to *somebody else*, edit it, cancel it, verify it |

Two consequences of using the design's four rather than inventing more:

**There is no `conversation.view`.** Reading is `message.send` plus a participant row, because
participation is the control that matters and a permission catalogue cannot express "this thread,
not that one".

**There is no `attachment.manage`.** The attachment routes declare `message.send` — every role
holds it, and it means only "may use the attachment mechanism". The check that matters is
decision 6.

**Creating a task for yourself needs only `task.view`; assigning one to somebody else needs
`task.assign`.** This is the design's own split read literally, and it is the right line: anybody
may write down their own work, and giving work to another person is a manager's act. It is also
what keeps a chef able to note "deep-clean the fryer" without holding a permission the design
deliberately withheld.

### 2 · Unread is a watermark, and the count is one comparison

`docs/schema.md` already decided this and eliminated the alternative: `message_read_receipt`
"would be the largest table in the schema — participants × messages".

`conversation_participant.last_read_message_id` is the watermark. The unread count for a
participant is the number of messages in that conversation created after the watermark's message,
which is one indexed count per conversation — and for the inbox, **one grouped query for all of
them**, not one per row. The inbox is the first screen anybody opens; an N+1 there would be the
module's defining bug, so `test_query_counts.py` gets an assertion that the inbox is a bounded
number of queries for any number of conversations.

`PATCH /conversations/{id}/read` moves the watermark **forward only**. A client that sends an older
message id gets 200 and no change, not a rewind — because two devices, and because "mark unread"
is not a feature we are building and a rewind would be its accidental implementation.

Messages you sent yourself never count as unread.

### 3 · A direct conversation between two people is one row, forever

`type='direct'` with exactly two participants is deduplicated: `POST /conversations` with
`type=direct` and a participant who already shares a direct thread with the actor **returns the
existing conversation with 200**, not a second one with 201. Without this, an inbox fills with
seven threads to the same person and the product looks broken.

Enforced in the database, not only in the service: a unique index on a canonicalised pair key
(`least(a,b), greatest(a,b)`) for direct conversations, so two simultaneous taps cannot both win.
The service catches the unique violation and returns the winner.

`group` conversations are not deduplicated. Two groups with the same members are two groups,
because they have different purposes and the members know what they are.

### 4 · Leaving a conversation is a fact with a date, not a deletion

`conversation_participant.left_at` exists precisely so that removing somebody does not rewrite
history. A participant who has left:

- keeps their messages visible to everyone else, attributed to them;
- can no longer read new messages or post;
- **can still be read about** — the thread shows "Priya left, 14 Sep" so that a thread whose
  membership changed mid-argument is readable afterwards.

Rejoining sets `left_at = NULL` on the same row rather than inserting a second one; the unique
constraint `(conversation_id, employee_id)` makes that the only option, which is the right one.

**A deactivated employee is not automatically removed.** M01 revokes their sessions immediately, so
they cannot read anything; their participant row stays so the thread still renders their name. The
alternative — sweeping participants on deactivation — would silently edit a record for a cosmetic
gain.

### 5 · The storage port, and the two things behind it

The single new abstraction in this module, and the only part worth arguing about.

```
StoragePort (protocol)
  put_url(key, content_type, size) -> UploadInstruction   # where the client PUTs bytes
  get_url(key, filename, expires)  -> str                 # short-lived download
  read_head(key, n)                -> bytes               # the first n bytes, for sniffing
  delete(key)                      -> None
  exists(key)                      -> ObjectFacts | None  # size + presence, from the store itself
```

Two adapters, chosen by one setting (`storage_driver`):

- **`filesystem`** — local development, every test, and staging until a bucket exists. Writes under
  `storage_root`. `put_url` returns a URL pointing back at this API (`PUT /attachments/{id}/content`),
  because a filesystem has no presigned upload.
- **`s3`** — boto3 against any S3-compatible endpoint (Cloudflare R2, GCS via HMAC interop,
  MinIO). `put_url` returns a genuine presigned PUT; the bytes never touch the API.

Two consequences follow, and both are tested:

**The API cannot assume it saw the bytes.** With the S3 driver it never does. So validation cannot
live in an upload handler — it lives in `POST /attachments/{id}/confirm`, which asks *the store*
how big the object is and reads its first bytes back. The same code path runs under both drivers,
which is the point: the filesystem driver is not a test double, it is the second production
implementation, and the sniffing test exercises the real one.

**Keys are generated, never derived from the filename.** `{restaurant_id}/{yyyy}/{mm}/{uuid7}{ext}`
— the tenant is in the key so a mis-scoped bucket policy is still tenant-shaped, the date prefix
keeps a directory listing usable, and the uuid means an uploaded `../../etc/passwd` is a *display
name* and nothing else. `file_name` is stored for display and is never a path.

**`storage_driver=filesystem` on staging loses uploads when Cloud Run recycles.** That is a real
limitation of the owner's chosen option, not a bug, and it is written at the top of the manual
script so a missing photo on the second day is understood rather than reported.

### 6 · You may attach to what you may write

There is one `attachment` table and six owner types. A permission per owner type would be six
permissions that drift apart; a single `attachment.upload` permission held by everyone would let a
waiter attach a file to a goods receipt.

So the route declares `attachment.manage` — which every role holds, and which means only "may use
the attachment mechanism at all" — and the service resolves the owner and asks the question that
actually matters: **may this actor write this object?** A message you sent, a task you own or
manage, a wastage event you logged, a complaint you may manage. The owner object is loaded through
its own repository, so tenant scope comes free and a cross-tenant `owner_id` is a 404 before any
file exists.

`owner_type` is the full six from `docs/schema.md`. Three get screens in this module (message,
task, wastage_event); `complaint`, `feedback` and `goods_receipt` get the authorization rule and no
UI, deliberately. **The trigger for building those screens is a person asking for one**, not a
tidiness urge — see `docs/backlog.md`.

### 7 · What an upload is allowed to be, and how that is checked

A restaurant uploads photographs. Occasionally a PDF invoice. Nothing else.

- **Allow-list, not deny-list**: `image/jpeg`, `image/png`, `image/webp`, `image/heic`,
  `application/pdf`. Anything else is refused at `POST /attachments`, before a key is issued.
- **The declared type is a claim, and the magic bytes are the evidence.** `confirm` reads the first
  bytes back from the store and refuses when they do not match the declared type. A `.jpg` whose
  first two bytes are `MZ` is refused and the object is deleted. This is the module's named test:
  *upload rejects a disguised executable*.
- **Size** is declared up front (refused over 10 MB — a phone photo is 2–5 MB) **and re-read from
  the store at confirm**, because the declared size is a client claim and the presigned PUT is not
  bound to it in every S3 implementation.
- **Unconfirmed attachments expire.** A row that is still `pending` after an hour is swept, along
  with any object behind it. Without the sweep, a bucket fills with orphans that no row references
  and no erasure reaches.

**Serving.** `docs/modules.md` says attachments are "served from a separate origin", which is the
right instinct — a stored HTML file on the API's own origin is stored XSS against every logged-in
session. With the S3 driver that holds naturally: the presigned URL is the bucket's host. With the
filesystem driver it cannot, so the defence is replaced in kind and stated as such:
`Content-Disposition: attachment` always, `X-Content-Type-Options: nosniff`, a restrictive
`Content-Security-Policy: sandbox`, and the allow-list above, which contains no executable or
markup type. A download route never renders.

### 8 · A message becomes a task and keeps its parentage

`POST /messages/{id}/promote` creates a task with `source_message_id` set, the message's body as
the starting description, and the conversation carried across: the new task's own thread is the
conversation it came from, not a fresh empty one. The message gains no state; promotion is not a
flag on it, it is a task that points back. Promoting the same message twice is allowed — two people
may genuinely owe two different pieces of work from one instruction — and the task list shows both.

Promoting a message into work for yourself needs `task.view`; promoting it onto somebody else
needs `task.assign`, exactly as creating a task does. The person who *sent* the message gets no
special standing from having sent it.

### 9 · Task status is a lifecycle, and `task_event` is the record

Seven states from `docs/schema.md`: `created → assigned → accepted → in_progress → completed →
verified`, with `cancelled` reachable from anything unfinished. The transitions are a table in the
service, not scattered `if` statements, and an illegal one is a 409 naming both states in words.

Who may move what:

- **The assignee** may `accept`, move to `in_progress`, and `complete`. Nobody else may complete
  work on somebody's behalf — that is the whole value of the record.
- **`task.assign`** may assign, reassign, edit, `cancel` and `verify`.
- A `task.assign` holder **may not verify a task they completed themselves** unless they are the
  owner. Same shape as M09's approver rule, and for the same reason: the person who did the work
  is not the person who says it was done.

`task_event` is append-only, one row per transition, with actor, both states, a note and
`occurred_at`. **Reassignment writes an event too**, with the note carrying from and to — a task
that changed hands twice reads as a history rather than as a current assignee.

An overdue task is derived (`due_at < now() AND status NOT IN (completed, verified, cancelled)`),
never stored. There is no background job flipping a flag, and the partial index in
`docs/schema.md` is the one that makes the derivation cheap.

### 10 · Deleting a message leaves a tombstone

`deleted_at` is set; body is nulled in the same statement. The row stays, the sender stays, and
the thread renders "message deleted". You may delete your own message; `task.assign` holders may
delete anyone's, which is the moderation valve a group chat eventually needs.

The body is nulled rather than kept, because "deleted" that a database admin can still read is a
lie told to the person who deleted it. The audit row records that a deletion happened, by whom, in
which conversation — **not what it said**.

### 11 · The stream is M08's, generalised once

`app/services/kitchen_stream.py` already solved this: a polled cursor rather than an in-process
broadcast or `LISTEN`/`NOTIFY`, a session per tick from the factory, inclusive replay from
`Last-Event-ID`, a re-checked session so a revoked token cannot hold a stream open all night, and a
self-ending 55-minute life inside Cloud Run's cap.

Every one of those reasons applies here unchanged, so the cursor-poll machinery moves to
`app/services/event_stream.py` as a generic piece parameterised by "what to fetch since revision N"
and "how to render one row", and **both** M08 and M11 use it. M08's behaviour must not change: its
existing tests (`test_kitchen_stream.py`, `test_kitchen_latency.py`) are the regression suite for
the extraction and are not edited to fit.

What `GET /messages/stream` yields:

- `message` — a new message in a conversation the viewer participates in, whole, so applying it
  twice is harmless;
- `unread` — the viewer's per-conversation unread counts, when they change;
- `task` — a task assigned to the viewer, or one of theirs changing state.

Tick is 2 s, not M08's 0.5 s: a kitchen display is a safety-critical two-metre read and an inbox is
not, and the database work is per open screen. **A conversation's revision is the message id
sequence**, so the cursor is monotonic per restaurant exactly as M08's is.

### 12 · Priority is a word, not a notification

`message.priority` (`normal|high|urgent`) and `task.priority` (`low|normal|high|urgent`) both
exist in the schema. In this module they are **sorting and colour, nothing else**: no push, no
email, no SMS. `notification` is M14's table and escalation tiers are M14's problem
(vision doc §25), and inventing a second notification path here would be the thing M14 then has to
delete.

An `urgent` message sorts the conversation to the top of every participant's inbox and renders in
the locked alert colour from `docs/ui/conventions.md`. That is the whole feature.

---

## Not in scope

Stated so they are decisions rather than omissions.

- **No guest messaging.** Decision above; a new ADR if ever.
- **No full-text search.** Decision in Research. The inbox has a filter by person and by unread.
- **No typing indicators, no read-by lists, no reactions, no voice notes.** The first two are the
  eliminated `message_read_receipt` table under another name. Reactions and voice notes are Phase 2
  if anyone
  asks.
- **No push notifications.** M14.
- **No message editing.** Delete and resend. An edited message with no visible history in a place
  where instructions are given is worse than no editing.
- **No recurring tasks.** "Clean the grease trap every Monday" is a real need and a real scheduler;
  it goes to the backlog with its trigger — build it when someone has created the same task by
  hand four weeks running.
- **No attachment screens for complaint, feedback or goods receipt.** Decision 6.
- **No announcements.** `conversation.type` keeps the value, because `docs/schema.md` declares it
  and a later module may want it, but **nothing in M11 creates one**. A broadcast nobody may reply
  to needs a permission the P1 design does not contain, and inventing one inside a migration is
  exactly what `test_the_shipped_catalogue_is_a_subset_of_the_p1_design` exists to stop. A group
  containing everybody already reaches everybody. The trigger for building it properly: somebody
  reports that an important broadcast got buried under replies.
- **No shift-scoped conversations.** M12 lands in the same run; a thread per shift is a tempting
  cross-module feature and neither module needs it.

---

## Deliverables

### Migrations — two

`0041_m11_communication`: six tables, their checks, their indexes, the canonical-pair unique index
for direct conversations, and the partial index on `task.due_at`. `downgrade()` drops all six.
Up→down→up against real Postgres.

`0042_m11_permissions`: the four P1 codes into `permission`, and their grants — three to every
system role, `task.assign` to owner and manager. A separate migration for the reason 0037
documents: a database that has already run 0002 never re-reads `permissions.json`.

`0043_m11_issues`: the issue-catalogue rows for this module's refusals (D11, D12) — a person reads
`message` and "Issue N", never a `code`.

`conversation_participant.last_read_message_id` → `message.id` is the circular FK
`docs/schema.md` §"Migration order" warns about; both tables are created in the same revision, so
the constraint is added after both exist rather than deferred to a follow-up.

### Backend

- `app/core/enums.py` — `ConversationType`, `MessagePriority`, `TaskStatus`, `TaskPriority`,
  `AttachmentOwnerType`, `AttachmentStatus`, mirrored into `frontend/src/shared/enums.ts` (the
  mirror test enforces it).
- `app/core/permissions.py` and `permissions.json` — the four P1 codes, with the descriptions a
  person reads in the role editor.
- `app/models/communication.py` — the six tables.
- `app/repositories/communication.py` — every query tenant-scoped; the inbox's single grouped
  unread query lives here.
- `app/services/conversations.py`, `app/services/tasks.py`, `app/services/attachments.py`.
- `app/services/event_stream.py` — the extracted cursor-poll, with `kitchen_stream.py` rewritten
  onto it.
- `app/storage/` — `port.py`, `filesystem.py`, `s3.py`, `factory.py`; `Settings` gains
  `storage_driver`, `storage_root`, `storage_bucket`, `storage_endpoint`, `storage_region`,
  `storage_access_key`, `storage_secret_key` (a `SecretStr`), `storage_url_ttl_seconds`.
  Boot fails when `storage_driver=s3` and any S3 setting is missing — the M00 rule.
- `app/schemas/communication.py` — every request `extra="forbid"`.
- The `pending`-attachment sweep, alongside the existing idempotency sweep.

### Endpoints

```
GET    /conversations                          message.send   inbox, cursor, unread counts
POST   /conversations                          message.send   direct dedupes to 200
GET    /conversations/{id}                     message.send   participants + title
PATCH  /conversations/{id}                     message.send   title (creator or task.assign), own mute
POST   /conversations/{id}/participants        message.send   add
DELETE /conversations/{id}/participants/{eid}  message.send   sets left_at; self always allowed
GET    /conversations/{id}/messages            message.send   cursor, newest first
PATCH  /conversations/{id}/read                message.send   watermark, forward only
POST   /messages                               message.send   Idempotency-Key required
DELETE /messages/{id}                          message.send   tombstone
POST   /messages/{id}/promote                  task.view      → task; onto another person: task.assign
GET    /messages/stream                        message.send   SSE
GET    /tasks                                  task.view      scoped: own unless task.assign
POST   /tasks                                  task.view      onto another person: task.assign
GET    /tasks/{id}                             task.view      with its events
PATCH  /tasks/{id}                             task.assign    title, description, priority, due
POST   /tasks/{id}/assign                      task.assign    writes an event
POST   /tasks/{id}/status                      task.complete  the transition table decides
POST   /attachments                            message.send   → row + upload instruction
PUT    /attachments/{id}/content               message.send   filesystem driver only
POST   /attachments/{id}/confirm               message.send   size + magic bytes, or refuse
GET    /attachments/{id}                       message.send   307 → short-lived signed URL
DELETE /attachments/{id}                       message.send   row + object
```

`POST /messages` carries `Idempotency-Key` for the reason `POST /wastage` does: a phone on a bad
connection in a kitchen, and a thumb that taps send twice.

### Frontend (staff bundle only)

Per `docs/ui/conventions.md` and the `restaurant-ui` skill.

- **Inbox** — conversations by `last_message_at`, urgent first, unread badge, one filter
  (all / unread), a new-conversation flow that finds people by name.
- **Thread** — messages newest at the bottom, sender and time, the attachment control, priority
  selector on send, promote-to-task on a message's menu, tombstones rendered as tombstones.
- **Task board** — columns by status, cards showing assignee, due time and an overdue treatment
  that is not colour alone (`docs/ui/conventions.md`).
- **Task detail** — the event history read as a history, the transition buttons the actor may
  actually use and no others rendered disabled-and-mysterious.
- **Attachment control** — pick, upload with real progress, retry on failure, thumbnail for images.
  Used by thread, task detail and the waste screen.
- **Waste screen** — the `requires_photo` nudge (decision 3 of the three owner decisions): a
  prominent ask, a recorded skip, and a save that still works.
- `communicationDiscipline.test.ts` — the frontend's own guard rail, in the shape of
  `wasteDiscipline.test.ts`: no message body in any analytics or log call, no staff-bundle import
  inside `src/guest/`, the attachment control refuses a type outside the allow-list before upload.

---

## Threat question — *what would an insider do with this?*

**Read a thread they are not in.** The only defence that scales is that every read is scoped by
participant row in the repository, never by a permission check in a handler. Generic suite 1 gets
victim rows for conversation, message, task and attachment.

**Upload a payload and get a colleague to open it.** Decision 7. The allow-list has no markup and
no executable type, the magic-byte check runs against the stored object rather than the request,
and the download route never renders.

**Read somebody else's attachment by guessing a URL.** Keys are uuid7-based and never guessable,
download URLs are short-lived and signed, and `GET /attachments/{id}` resolves the owner object
through its repository before signing anything — so a valid id belonging to another tenant is a
404, not a redirect.

**Erase an instruction they were given.** Deletion leaves a tombstone and an audit row; task
history is append-only; reassignment is an event and not an overwrite. The manager who says "I
never told you to comp that table" is the case the record exists for.

**Post as somebody else.** `sender_employee_id` comes from the actor, never the body.

**Exfiltrate the staff list.** The people-picker for a new conversation returns active employees of
this restaurant only, name and role, no phone, no email, no employment terms — it is already what
`employee.view` shows, and the picker uses the same serialiser rather than a wider one.

---

## Acceptance criteria

1. Every role in the catalogue, including `cleaner`, can open the inbox, send a message, write
   down a task for itself and move one it was assigned — asserted over the catalogue, so a role
   added later fails the test rather than silently losing access. No permission code outside the
   P1 design ships: the subset test passes untouched.
2. Unread counts are correct in a group thread when 3 of 5 participants have read it, and a
   participant's own messages never count as unread.
3. The inbox costs a bounded number of queries for 1 conversation and for 50.
4. `POST /conversations` with `type=direct` twice returns the same conversation id, including when
   the two requests race.
5. The watermark never moves backwards.
6. A message sent twice with the same `Idempotency-Key` appears once.
7. A disguised executable — `.jpg` extension, `image/jpeg` declared, `MZ` first bytes — is refused
   at confirm, and the stored object is deleted.
8. A file larger than the declared size is refused at confirm, under both drivers.
9. A `pending` attachment older than an hour is swept, with its object.
10. `GET /attachments/{id}` for another restaurant's attachment is 404, and no URL is signed.
11. A downloaded attachment arrives with `Content-Disposition: attachment` and `nosniff`.
12. Promoting a message creates a task with `source_message_id` and the original conversation.
13. An illegal task transition is 409 and names both states in words a person reads.
14. Only the assignee may complete; a `task.verify` holder may not verify their own completion
    unless they are the owner.
15. Reassignment appends an event; the previous assignee remains readable in the history.
16. Overdue is derived — no row changes when a due time passes.
17. Deleting a message leaves the row, the sender and an audit entry, and no body anywhere.
18. A left participant reads nothing new and posts nothing, and their old messages still render.
19. `GET /messages/stream` delivers a new message within 2 s, replays inclusively from
    `Last-Event-ID` after a drop, and ends itself before Cloud Run's cap.
20. A stream open on a revoked session stops within one tick.
21. **M08 is unchanged**: `test_kitchen_stream.py` and `test_kitchen_latency.py` pass unedited
    after the extraction.
22. The waste screen asks for a photo on a `requires_photo` reason, records that it was skipped,
    and saves either way.
23. No message body appears in any log record, at any level.
24. Boot fails when `storage_driver=s3` and a required S3 setting is absent.
25. Generic suites 1–5 pass, with new victim rows for all six tables.

---

## Chunks — four PRs against `feat/m11-communication`

**A · Schema, enums, permissions.** Migrations 0041 and 0042, models, the enum mirror, the four
P1 permissions and their grants, `test_communication_schema.py`. Ends with up→down→up green and
every role holding the three universal permissions.

**B · The storage port.** `app/storage/`, both drivers, settings and their boot-time validation,
the `attachment` service, its four endpoints, the sweep, and `test_attachments.py` — including the
disguised executable and the size lie, run against **both** drivers by parameterising the fixture.
Self-contained and independently reviewable, which is why it is not folded into C.

**C · Conversations, messages, the stream.** Repository, services, endpoints, the extraction of
`event_stream.py` with M08 rewritten onto it, `test_conversations.py`, `test_messages.py`,
`test_event_stream.py`, the query-count assertion, generic-suite rows.

**D · Tasks, then the frontend.** Task service with its transition table, endpoints, events,
promotion, `test_tasks.py`; then all five screens, the attachment control, the waste nudge, and
`communicationDiscipline.test.ts`. Ends with `make check` clean and the manual script written.
