# M11 · Communication & Tasks — Manual Test

**Module:** M11 · **Built:** 2026-09-18 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m11-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins that
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**,
**manager@spicegarden.test**, **kitchen1@spicegarden.test** (a chef),
**waiter1@spicegarden.test** and **cleaner1@spicegarden.test**.
**manager@tandoorhouse.test** is the other tenant.

**Read this before you start, because it will otherwise look like a bug.** Staging stores uploaded
files on the container's own disk, which is memory: **a photo you attach today may be gone
tomorrow**, because Cloud Run recycles the instance. That is the storage driver you chose on
2026-09-18 and it is a deliberate trade — nothing in this module was waiting on a bucket existing.
Switching staging to real object storage is three environment variables and no code. Within one
session, an attachment works exactly as it will in production.

**The question this module has to answer is not "does chat work".** Chat is table stakes and we
lose that comparison to WhatsApp on day one. The question is section D: **is a message one tap from
being work somebody is accountable for, and does the record survive an argument?** If D feels like
a feature rather than the reason to use this instead of a WhatsApp group, tell me — that is the
module failing, whatever else passes.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · everybody talks** | Verified over the whole role catalogue, cleaner included. **A3 is the one worth doing by hand** |
| **B · unread** | Verified: three of five having read a group thread, own messages never unread, the watermark never moving backwards. **B4 is a judgement** |
| **C · one thread per person** | Verified, including two people tapping at the same moment. **C1 by hand** |
| **D · a message becomes work** | Verified mechanically. **Entirely yours as a judgement — this is the module** |
| **E · the record** | Verified: only the assignee completes, nobody signs off their own work, every handover appends. **E4 is the question** |
| **F · files** | Verified against a real bucket and a real disk, including a disguised executable. **F3 and F5 by hand** |
| **G · live** | Verified: delivery, reconnect, and a revoked session closing the stream. **G1 by hand, on two devices** |
| **H · who may see what** | Verified by the permission matrix and the tenant probe over every route. **H1 and H3 by hand** |
| **I · exploratory** | Not run. Yours |

Short of time? Do **D**, then **G1**, then the I charter. D is the whole argument for the module and
no test can judge it; G1 is the thing people notice in the first minute.

---

## A · Everybody talks, including the cleaner

`cleaner` held **zero** permissions before this module. The person who finds the broken freezer at
6am is exactly the person who had no way to tell anybody.

| # | Step | Expect |
|---|---|---|
| A1 | Sign in as **cleaner1**. Look at the header | **Messages** and **Tasks** are there. So is **My shifts** (M12) |
| A2 | Open **Messages**, start a conversation with **manager**, send "Freezer in the back is warm" | It sends. No permission error anywhere |
| A3 | Sign in as **manager** on another device or a private window. Open Messages | The cleaner's message is there, with their name on it, and the thread shows **1 unread** before you open it |
| A4 | As **cleaner1**, try the URL `/settings` directly | Refused with a readable message, not a blank screen. The cleaner can talk; they cannot configure a restaurant |

---

## B · Unread, and what it counts

| # | Step | Expect |
|---|---|---|
| B1 | As **owner**, make a group with **manager**, **kitchen1** and **waiter1**. Send two messages | Your own inbox shows the thread with **no** unread badge. A badge because you spoke is how people learn to ignore badges |
| B2 | As **kitchen1**, open Messages without opening the thread | **2 unread** |
| B3 | Open the thread, then go back to Messages | **0 unread**. Opening it is what marks it read — there is nothing to press |
| B4 | As **waiter1**, look at the same inbox | **2 unread**, unaffected by what the chef did. Does the count match what you would expect if you had been away for an hour? |
| B5 | As **owner**, send one more with priority **Urgent** | Every other person's inbox shows that thread at the top with an **Urgent** badge — a word, not only a colour |

---

## C · One thread per person, forever

| # | Step | Expect |
|---|---|---|
| C1 | As **owner**, start a conversation with **manager**. Go back, and start one with **manager** again | You land in the **same** thread. Not a second one. An inbox with seven threads to the same person is how a messaging feature looks broken |
| C2 | As **manager**, start one with **owner** | The same thread again, from the other side, with the earlier messages in it |
| C3 | In a group, remove somebody, then look at the thread | Their old messages are still there with their name on. They are shown as having left. Nothing was rewritten |
| C4 | Sign in as the person you removed and open Messages | The thread is gone from their inbox. They read nothing new |

---

## D · A message becomes work — **this is the module**

| # | Step | Expect |
|---|---|---|
| D1 | As **manager**, send into a group: "AC repair man coming at 4. Let him in." | Sent |
| D2 | On that message, press **Make this a task** | A task exists. Open **Tasks** |
| D3 | Open the task | Its title is the first line; the whole message is the description. It knows which message it came from |
| D4 | Press **Make this a task** on the same message again | A second task. Deliberate: two people may owe two different pieces of work from one instruction |
| D5 | **The judgement.** Imagine this is a real WhatsApp group on a real Tuesday. Would you use this instead? | Your answer, in words. If it is "no", say why — the answer is worth more than everything else in this file |

---

## E · The record that survives an argument

| # | Step | Expect |
|---|---|---|
| E1 | As **manager**, create a task assigned to **kitchen1**: "Deep-clean the fryer", due today | On the board under **Assigned** |
| E2 | As **manager**, try to mark it finished | You cannot. Only the person it is assigned to can, and the screen says so rather than showing a button that fails |
| E3 | As **kitchen1**, accept it, start it, finish it | Each step is one tap. The task moves to **Finished — waiting to be checked** |
| E4 | As **manager**, open the task and read **What has happened** | Every step, with who did it and when. **Does it read as a history a person could use in a disagreement?** |
| E5 | As **manager**, send it back with "Grease still in the tray" | It goes back to in-progress, and the completion is cleared — it is not finished while it is being done again |
| E6 | As **kitchen1**, finish it again. As **manager**, check and close it | Closed, with your name on the check |
| E7 | As **manager**, create a task for **yourself**, finish it, then try to check it | Refused: *somebody else has to check work you finished yourself*. The owner is the exception — try it as **owner** and it works |
| E8 | As **manager**, move E1's task to **waiter1** with the reason "chef is off" | The history shows the handover, from and to, with your reason. The previous person is still readable |

---

## F · Files

| # | Step | Expect |
|---|---|---|
| F1 | As **kitchen1**, attach a photo to a message | It uploads, and appears as a link with its filename. Opening it downloads rather than showing it in the page — deliberate, and the reason is in `docs/security.md` |
| F2 | Rename any `.exe` on your machine to `photo.jpg` and try to attach it | Refused. It says the file is not the kind of file it claims to be. Nothing is left behind |
| F3 | Attach a file over 10 MB | Refused **before** it uploads, so you do not wait for it |
| F4 | Log waste as **kitchen1** with the reason **Expired** (which wants a photo) | After logging, the screen asks for a photo — **and Log something else is right there**. The waste is already saved |
| F5 | Skip the photo | The log stands. Nothing is lost, nothing is nagged twice. **Does the ask feel like help or like an obstacle?** That is the whole question |
| F6 | Attach a photo to a waste log somebody else made | Refused. You may attach to what you may write |

---

## G · Live

| # | Step | Expect |
|---|---|---|
| G1 | Two devices, two people, same thread open. Send from one | It appears on the other within a couple of seconds, without a refresh |
| G2 | Turn the wifi off on one device for thirty seconds, then on | The banner says it is reconnecting, then stops. Anything sent while it was off arrives — **nothing is missing** |
| G3 | Leave a thread open for ten minutes and send occasionally | Still live. No duplicates, nothing arriving twice |
| G4 | As **owner**, deactivate a user who has Messages open, from **Staff** | Their screen stops being live within a few seconds. A revoked session does not keep a stream open |

---

## H · Who may see what

| # | Step | Expect |
|---|---|---|
| H1 | As **waiter1**, ask **manager** for the address of a conversation you are not in and paste it | Not found. Not "forbidden" — not found, because telling the two apart maps what exists |
| H2 | As **waiter1**, try to create a task assigned to **kitchen1** | Refused: only a manager gives work to somebody else. Creating one for yourself works |
| H3 | Sign in as **manager@tandoorhouse.test** and paste any address from Spice Garden — a conversation, a task, an attachment | Every one is not found. This is the probe that matters most in the whole product |
| H4 | As **kitchen1**, look at the Tasks board | Only your own work. The whole board is a manager's view |

---

## I · Exploratory charter — 20 minutes

**Charter:** *Use this as your restaurant's actual communication for twenty minutes, with two
people, and try to make it lose something.*

Ideas: send while the other person is typing; delete a message somebody has already replied to;
promote a message, then delete the message; attach a photo and remove the person from the thread;
send an urgent message to somebody who has muted the thread; start a conversation with somebody who
has just been deactivated; reload mid-send.

Write down anything that surprised you, whether or not it is a bug. **Especially write down anything
you found yourself wanting to do that the screen would not let you** — that is the list I cannot
generate.
