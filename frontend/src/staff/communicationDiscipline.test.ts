// The four rules M11's screens live or die by, checked by a machine.
//
// Same shape as `wasteDiscipline.test.ts` and `kdsReadability.test.ts`: a rule that lives only in
// prose is a rule the next screen written in a hurry quietly skips. Each of these has a reason in
// the spec, and each would be invisible in review until it mattered.
//
// 1. **No message body reaches a log or an analytics call.** A body is unstructured and therefore
//    unclassifiable — a guest's phone number, a supplier's price, somebody's medical reason for
//    being off — so the only safe assumption is that it contains everything. The server refuses to
//    log one; a browser must not be the hole.
// 2. **The upload allow-list is checked before the file is sent.** Not as a substitute for the
//    server, which reads the stored object's first bytes back, but because refusing a 40 MB video
//    *after* uploading it over a restaurant's connection wastes a minute for an answer we had when
//    the person picked it.
// 3. **This session's token never goes to a bucket.** An upload URL the server signed belongs to
//    another host; attaching our `Authorization` header to it hands a live credential away. The
//    raw `fetch` for a signed URL therefore lives in `shared/api.ts` and nowhere else.
// 4. **Nothing in `src/guest/` imports any of this.** ADR 0009's boundary, and M11 has no guest
//    surface at all: there is no route under `/guest` and no guest token is accepted anywhere in
//    it. A communication module is exactly where somebody would later be tempted.
import { describe, expect, it } from 'vitest';

const screens = import.meta.glob<string>('./screens/{Inbox,Thread,Tasks,Task}Screen.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const api = import.meta.glob<string>('./api/communication.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const control = import.meta.glob<string>('./components/AttachmentControl.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const guest = import.meta.glob<string>('../guest/**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

function only(sources: Record<string, string>, name: string): string {
  const found = Object.entries(sources).find(([path]) => path.endsWith(name));
  expect(found, `${name} was not found — this test would otherwise pass vacuously`).toBeDefined();
  return withoutComments(found?.[1] ?? '');
}

describe('the communication screens keep their rules', () => {
  it('reads the files it checks, so an empty parse cannot pass', () => {
    expect(Object.keys(screens).length).toBeGreaterThanOrEqual(4);
    expect(Object.keys(api).length).toBe(1);
    expect(Object.keys(control).length).toBe(1);
  });

  // Rule 1.
  it('never puts a message body into a log or an analytics call', () => {
    const suspicious = /\b(console\.(log|info|warn|error)|track|analytics)\b/;
    Object.entries(screens).forEach(([path, source]) => {
      expect(withoutComments(source), `${path} logs something`).not.toMatch(suspicious);
    });
    expect(only(api, '/communication.ts')).not.toMatch(suspicious);
  });

  // Rule 2. Both halves: the type and the size, before `mutate` is called.
  it('checks the allow-list and the size before uploading anything', () => {
    const code = only(control, '/AttachmentControl.tsx');
    expect(code).toContain('ALLOWED_UPLOAD_TYPES');
    expect(code).toContain('MAX_UPLOAD_BYTES');
    const guard = code.indexOf('MAX_UPLOAD_BYTES');
    const send = code.indexOf('upload.mutate');
    expect(guard, 'the size check runs before the upload, not after it').toBeLessThan(send);
  });

  // Rule 3. The one `fetch` in this module's path is the one in `shared/api.ts`.
  it('never calls fetch itself, so no token can reach a bucket', () => {
    expect(only(api, '/communication.ts')).not.toMatch(/\bfetch\(/);
    Object.entries(screens).forEach(([path, source]) => {
      expect(withoutComments(source), `${path} calls fetch`).not.toMatch(/\bfetch\(/);
    });
  });

  // Rule 4. ADR 0009, as a build failure rather than a promise.
  it('is not imported anywhere in the guest bundle', () => {
    Object.entries(guest).forEach(([path, source]) => {
      expect(withoutComments(source), `${path} imports staff communication code`).not.toMatch(
        /@staff\/(api\/communication|screens\/(Inbox|Thread|Tasks|Task)Screen|components\/AttachmentControl)/,
      );
    });
  });

  // Rule 5, found the hard way on 2026-09-19: every attachment in the product returned
  // `auth.required` when opened, and had since M11 shipped.
  //
  // This product authenticates with a Bearer token in an `Authorization` header, held in memory.
  // **A browser following an `<a href>` sends cookies and cannot send that header**, so a link
  // straight at `/api/v1/staff/attachments/{id}` is a request that can only ever be refused —
  // `GET /attachments/{id}` requires an actor holding `message.send`.
  //
  // Rule 3 above reasons carefully about the *upload* leg and where the token may go. The download
  // leg was left as a plain link. This is the other half of the same rule.
  it('never opens an attachment with a bare link, because a browser cannot authenticate one', () => {
    const code = only(control, '/AttachmentControl.tsx');

    // Non-vacuous: the control must still render attachments at all.
    expect(code).toContain('attachment.file_name');

    // The defect, stated directly: an href the browser cannot authenticate.
    expect(
      code,
      'an attachment is opened with a bare href, which a browser cannot authenticate',
    ).not.toMatch(/href=\{attachmentHref/);
  });

  // The waste nudge is a nudge. The owner decided this on 2026-09-18 and `docs/waste-model.md`
  // is why: anything that makes honest reporting harder gets you less honest reporting, not more
  // photographs. So the photo is asked for *after* the log is saved, and nothing gates the save.
  it('asks for a waste photo without blocking the log', () => {
    const waste = import.meta.glob<string>('./screens/WasteScreen.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    });
    const code = only(waste, '/WasteScreen.tsx');
    expect(code).toContain('AttachmentControl');
    // The control appears inside `Logged` — the screen shown after the event exists — and the
    // submit path never mentions it.
    const logged = code.indexOf('function Logged');
    expect(code.indexOf('AttachmentControl', logged)).toBeGreaterThan(logged);
    const submit = code.slice(code.indexOf('const submit'), code.indexOf('if (logged !== null)'));
    expect(submit).not.toContain('AttachmentControl');
    expect(submit).not.toContain('requires_photo');
  });
});
