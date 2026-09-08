# guest/

This directory is the ADR 0009 seam, held open on purpose. It is empty until M10.

ADR 0009 (`docs/decisions/0009-two-personas-two-applications.md`) separates employee and customer
**structurally**, not with a `role` check. The customer PWA is therefore a second Rollup entry
point, not a route inside the staff app - the commented-out `guest:` line in `frontend/vite.config.ts`
is the whole change, and it lands in M10.

The rule that makes the seam worth anything:

> **No staff code may ever be imported into `guest/`.** Not a component, not a hook, not a type, not
> a constant.

If the guest bundle contains staff code, it ships admin routes to discover and permission strings to
enumerate to thousands of strangers on a hostile network - which is precisely the failure ADR 0009
exists to prevent. Shared, persona-neutral code lives in `src/shared/`; anything that knows about
staff belongs in `src/staff/` and stays there. Duplication between the two personas is the feature,
not a smell: it means a field added for staff cannot silently appear in a guest response.
