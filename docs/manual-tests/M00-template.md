# MXX · <Module Name> — Manual Test

**Module:** MXX · **Est. time:** __ min · **Tester:** you · **Environment:** staging

---

## Preconditions

- Staging URL:
- Logins needed (role → email → password):
- Seed state required (e.g. "at least one open order on table T4"):
- Use a private/incognito window.

---

## A · Happy path

The module used correctly, by the person it is built for, in the order they would really do it.

| # | Step | Expected | P/F |
|---|---|---|---|
| A1 | | | ☐ |
| A2 | | | ☐ |

---

## B · Validation

Bad input, missing input, wrong input. Every error must be plain English with no internal detail.

| # | Step | Expected | P/F |
|---|---|---|---|
| B1 | | | ☐ |

---

## C · Permissions

Every role that touches this module, including the roles that must **not**.

| # | Step | Expected | P/F |
|---|---|---|---|
| C1 | | | ☐ |

---

## D · Security probes

Always includes, adapted to this module:
- Cross-restaurant access by editing an id in the URL → denied
- A lower-privileged role reaching a higher-privileged URL directly → denied
- Back button after logout → no data
- Guest/QR token against a staff URL → denied (where the module has a guest surface)

| # | Step | Expected | P/F |
|---|---|---|---|
| D1 | | | ☐ |

---

## E · Usability

Real conditions: on a phone, one-handed, in a hurry, on bad wifi. For kitchen screens, read from
two metres away.

| # | Step | Expected | P/F |
|---|---|---|---|
| E1 | | | ☐ |

---

## F · Exploratory charter — 10 minutes

**Goal: <one specific sentence — what are you trying to break?>**

Notes:

```


```

---

## Result

- Steps passed: ____ / ____
- Failures (step number → expected → saw):

```


```
