# M11 · Communication & Tasks — Build Log

Spec: `docs/modules/M11-communication-spec.md`. Manual script:
`docs/manual-tests/M11-communication.md`.

---

## State

| Chunk | What | State |
|---|---|---|
| A | Migrations 0041–0043, models, enums, the four P1 permissions, 12 schema tests | ✅ committed |
| B | The storage port, both drivers, the attachment service and its routes, 51 tests | ✅ committed |
| C | Conversations, messages, tasks, and M08's stream generalised; 46 tests | ✅ committed |
| D | Five screens, the attachment control, M09's photo nudge, the discipline test | ✅ committed |
| — | Manual pass | **Owner's** |

Built in one autonomous run on 2026-09-18, on `feat/m11-communication`.

---

## The three decisions taken before the spec was written

Guessing any of them wrong meant rebuilding, so they went to the owner first
(2026-09-18):

1. **Attachments get a storage port with two drivers** — filesystem and S3 — so nothing in the
   module waits on a bucket existing. Staging runs the filesystem driver and loses uploads when
   Cloud Run recycles; that limitation is stated at the top of the manual script rather than
   discovered on the second day.
2. **Messages arrive over SSE**, by generalising M08's cursor-poll stream rather than writing a
   second one.
3. **M09's `requires_photo` becomes a nudge, not a block.**

---

## What reading the P1 design first removed

The spec's first draft invented seven permissions. `seed/organization.yaml` — written in P1 and
guarded by `test_the_shipped_catalogue_is_a_subset_of_the_p1_design` — already contained exactly
four comms codes, and already granted three of them to **every role including `cleaner`**, which
was the spec's own decision 1 arrived at independently.

Reading it before writing a migration removed:

- **`conversation.view`** — reading is `message.send` plus a participant row. Participation is the
  control a permission catalogue cannot express, and a repository scope can.
- **`attachment.manage`** — the routes declare `message.send`; the question that decides the matter
  is whether the actor may write the owner object.
- **`task.manage`/`task.verify`** — the design's `task.assign` covers both, and its split reads
  better than the invention: creating a task for yourself is `task.view`, giving work to somebody
  else is `task.assign`. That is what keeps a chef able to note "deep-clean the fryer" without a
  permission the design withheld on purpose.
- **Announcements, entirely.** A broadcast nobody may reply to needs a permission the design does
  not contain, and a group containing everybody already reaches everybody. Backlogged with its
  trigger: somebody reports that an important broadcast got buried under replies.

Fourth module in a row where the P1 design turned out to be ahead of the spec.

---

## What the build found

### 1 · A refused upload deleted the object and kept the row

The test was written first, as the process requires, and failed:

```
FAILED tests/test_attachments.py::TestAttachingAFile::
       test_a_disguised_executable_is_refused_and_leaves_nothing_behind
E   assert <app.models.communication.Attachment object at 0x...> is None
```

`confirm` deletes the row and the object and then raises — and the error handler rolls the
request's transaction back, so the object went and the row survived. Exactly the worst
combination: an orphaned row pointing at nothing, swept an hour later, with nothing to explain it
in between.

The commit now happens inside the `except`, with the reasoning at the call site. **This is M08's
vanishing-write bug one layer up**, and the third time this codebase has met the shape.

### 2 · Sending completed work back was caught by the assignee-only rule

`completed → in_progress` is in `_ASSIGNEE_ONLY`, so the one person who must *not* decide whether
work passed — the person who did it — was the only person able to say it had not. The transition
now checks where it is coming *from*: from `completed`, a move to `in_progress` is a refusal to
sign off, and that is `task.assign`'s act.

Found by a test written from the spec's own words rather than from the code.

### 3 · `minio/minio` on Docker Hub no longer exists

A pull answers *"repository does not exist or may require docker login"*, which reads like an
authentication problem and is not one — MinIO moved to quay.io. Recorded in
`tests/test_attachments.py`'s docstring because the next person will otherwise spend twenty minutes
on `docker login`. The image is pinned by digest, for the reason `uv` is pinned.

### 4 · Two uncatalogued error codes from the staging work

`seed.no_password` and `seed.committed_password` arrived with the m10 staging-seed commits without
issue numbers. `test_issue_catalogue.py` found them at this module's gate, which is exactly what
that test is for. Both are in 0043 with M11's forty.

### 5 · Three frontend rules the gate enforced, all of them correctly

- eslint's `no-restricted-globals` refused the bucket upload. The raw `fetch` for a signed URL
  moved to `shared/api.ts` as `putToSignedUrl`, with the reason it sends no `Authorization` header
  written where the call is. **The rule was right**: a token attached to a bucket URL hands a live
  credential to another host.
- the complexity budget refused `MessageRow` twice, and both splits improved it.
- the brand checklist refused both detail screens for having no way back — §8.7, the rule that
  exists because the owner once had to close a tab to leave a screen.

---

## The extraction, and how it was kept honest

`app/services/event_stream.py` is M08's polling loop, moved. The regression suite for the move is
**M08's own tests, unedited**: `test_kitchen_stream.py`, `test_kitchen_latency.py` and
`test_kitchen_endpoints.py`, 31 tests, green before and after. Acceptance criterion 21.

What did **not** move is the counter. `kot_stream_cursor` and `comm_stream_cursor` stay two tables:
a Postgres sequence is global and a global cursor leaks how busy every other tenant is, and sharing
one row would make every message bump the kitchen's revision and wake every display in the
building.

---

## Deviations from the spec, each with its reason

| Spec said | Built | Why |
|---|---|---|
| Three SSE event kinds: `message`, `task`, `unread` | Two: `message`, `task` | A count pushed down a socket is a second source of truth for something one indexed query already answers, and the two drift the first time an event is dropped or replayed. The client refetches the inbox instead |
| Seven new permissions | Four, all from the P1 design | Above |
| Announcements | Not built | Above |
| Migrations 0037–0038 | 0041–0043 | The tree was at 0040, not 0036 |
| Attachment screens for complaint, feedback, goods receipt | Not built | Spec decision 6 already deferred them; the trigger is a person asking for one |

---

## The test files this module owes, and what each one holds

| File | What it holds |
|---|---|
| `test_communication_schema.py` | Migration 0041 against real Postgres: 12 constraints, each proving a refusal rather than a happy path |
| `test_attachments.py` | The media rules as pure functions; the driver contract against **both** adapters, one of them a real MinIO container; the whole upload journey over HTTP; the disguised executable; the sweep |
| `test_conversations.py` | Every role posting, the watermark in a group thread, one direct thread per pair, a left participant, the tombstone, the stream, and the inbox's query count |
| `test_tasks.py` | The transition table, who may move what, the verification rule, the record, promotion, and what each role can see |
| `test_generic_suites.py` | Victim rows for all six tables plus the stream's registration |
| `communicationDiscipline.test.ts` | No body in any log; the allow-list checked before upload; no `fetch` in this module's path; nothing imported into `src/guest/` |
