"""The audit decorator. One path to `audit_log`, declared at the method it records.

`docs/modules.md` states the rule and its reason in one line: *"audit written by a service-layer
decorator, not by hand at each call site — hand-written audit calls get forgotten exactly where
they matter."*

**That is a threat model, not a style preference.** An insider's most valuable act is the one
nobody recorded, and the call sites most likely to be missed are the rare ones: the manual price
override, the adjustment at the end of a bad month, the role granted at eleven at night. Each is a
path somebody wrote once, in a hurry, and tested once.

**The real deliverable is `tests/test_audit_declarations.py`**, which fails the build when a
mutating service method declares neither an audit nor an exemption — exactly as M00's suite fails
the build when a route declares no permission. This module is what makes that test satisfiable.

Four rules it keeps, each of which a hand-written call could break and did:

**It is explicit.** The action string, the entity and the key are all written at the method. A
reviewer reading the signature can say what the row will contain. Nothing here infers an action
from a method name, and nothing writes a row a reader could not predict.

**It reads through a repository.** The before and after states are loaded tenant-scoped
(`AuditSubjectRepository`), because a decorator doing `session.get(Model, id)` would be the one
unscoped read in the codebase — and invariant 1 has no exception for convenience.

**It never records a credential.** `_REDACTED` drops anything whose column name looks like a
secret. The old helpers redacted *at the call site*, which worked until somebody added a column.

**It records a reason when the act has one.** `audit_log` has no `reason` column; a why goes in the
metadata block, beside the values it explains, the way M12's correction and M07's waiter handover
already do.
"""

from __future__ import annotations

import functools
import inspect
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.models.audit import AuditLog

# Column names whose values never reach the trail. The audit table is readable by anyone holding
# `audit.view`, so a password hash landing here would be a leak with a long tail — and unlike a log
# line it is not rotated away.
_REDACTED = ("password", "token", "secret", "hash", "salt", "otp")

# Not changes, and in every diff if they were. The row's own `occurred_at` is when the change
# happened; `updated_at` moving from one timestamp to another is the fact that something was
# written, which the row's existence already says. `created_at` never moves at all.
_NOT_A_CHANGE = ("created_at", "updated_at")


@runtime_checkable
class AuditedService(Protocol):
    """What `@audited` needs from the service it is applied to.

    A Protocol rather than a base class: the ten services this replaces already have their own
    constructors and their own repositories, and making them inherit from something would be a
    change to every one of them for the decorator's convenience.
    """

    session: AsyncSession


def record(
    session: AsyncSession,
    actor: Actor,
    *,
    action: str,
    entity: str,
    entity_id: uuid.UUID,
    old: Mapping[str, object] | None = None,
    new: Mapping[str, object] | None = None,
    reason: str | None = None,
) -> None:
    """Write one audit row. **The only place in this codebase that constructs an `AuditLog`.**

    `@audited` calls this, and so do the handful of methods that legitimately record a *second*
    entity: posting a goods receipt also reprices a stock item, and those are two facts about two
    tables. Such a call is never the method's only record — the method still declares its own with
    the decorator, which is what `tests/test_audit_declarations.py` enforces.

    Values are scrubbed here rather than at the call site. The old helpers redacted where the
    dictionary was built, which worked for exactly as long as nobody added a column.
    """
    session.add(
        AuditLog(
            restaurant_id=actor.restaurant_id,
            actor_employee_id=actor.employee_id,
            action=action,
            entity_type=entity,
            entity_id=entity_id,
            old_value=None if old is None else scrub(old),
            new_value=None if new is None else scrub(new),
            audit_metadata=None if reason is None else {"reason": reason},
        )
    )


def record_unattributed(
    session: AsyncSession,
    *,
    restaurant_id: uuid.UUID,
    action: str,
    entity: str,
    entity_id: uuid.UUID,
    new: Mapping[str, object] | None = None,
) -> None:
    """One row with no actor behind it. **`app/bootstrap.py` is the only caller, and only it can
    be.**

    Bootstrap creates the first organization, the first restaurant and the first owner from the
    command line: nobody is signed in, because that is the point of the command. `audit_log.
    actor_employee_id` is nullable for exactly this, and an unattributed row is worth more than no
    row — the alternative is that the most privileged act in the product's life is the one act it
    does not record.

    A separate function rather than an optional `actor` on `record`, so that "there was nobody" has
    to be stated on purpose and cannot be reached by passing `None` from a service that lost track
    of who was acting.
    """
    session.add(
        AuditLog(
            restaurant_id=restaurant_id,
            actor_employee_id=None,
            action=action,
            entity_type=entity,
            entity_id=entity_id,
            new_value=None if new is None else scrub(new),
        )
    )


def audited(
    action: str,
    *,
    entity: str,
    key: str | None = None,
    reason: str | None = None,
) -> Callable[..., Any]:
    """Record what this method changed.

    `action`  — the stable string a person filters on: `"order.void"`, `"menu_item.price"`.
    `entity`  — the **table name** of the thing changed. Resolved against SQLAlchemy's own mapper
                registry, so an entity that does not exist fails at import rather than writing a
                row nobody can join.
    `key`     — the parameter holding the entity's id. Omit it for a method that *creates* the
                thing: the id is then taken from what the method returns, because before the call
                there was nothing to have an id.
    `reason`  — the parameter holding a why, if the act has one. It goes in the metadata block
                beside the values it explains (`audit_log` has no `reason` column).

    Both `key` and `reason` are checked against the signature **at decoration time**, so a renamed
    parameter is an import error rather than a row that silently stops being written.
    """

    def decorate(
        method: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        signature = inspect.signature(method)
        _check_parameter(method, signature, "actor")
        if key is not None:
            _check_parameter(method, signature, key)
        if reason is not None:
            _check_parameter(method, signature, reason)

        @functools.wraps(method)
        async def wrapper(self: AuditedService, *args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            actor = bound.arguments["actor"]
            if not isinstance(actor, Actor):  # pragma: no cover - the signature check precedes it
                raise TypeError(f"{method.__qualname__}: actor is not an Actor")

            subject = _subjects(self, actor)
            entity_id = None if key is None else bound.arguments[key]
            before = None if entity_id is None else await subject.snapshot(entity, entity_id)

            result = await method(self, *args, **kwargs)

            if entity_id is None:
                entity_id = _id_of(method, result)
            # Flushed first, so the after-state is what the database holds rather than what the
            # session happens to have in memory — a method that issued an UPDATE statement leaves
            # the mapped object stale until it does. The snapshot then reads *columns*, touching no
            # identity map, so nothing the wrapped method returned is disturbed.
            await self.session.flush()
            after = await subject.snapshot(entity, entity_id)

            record(
                self.session,
                actor,
                action=action,
                entity=entity,
                entity_id=entity_id,
                old=_changed(before, after),
                new=_changed(after, before),
                reason=None if reason is None else bound.arguments.get(reason),
            )
            return result

        return wrapper

    return decorate


# --------------------------------------------------------------------------- internals


def _check_parameter(method: Callable[..., Any], signature: inspect.Signature, name: str) -> None:
    """A wrong name is an import error, not a missing row.

    The failure this prevents is quiet: rename `order_id` to `bill_id`, and a decorator looking up
    the old name would raise at the first void — or, worse, a version of this that shrugged would
    write rows with no subject for a year.
    """
    if name not in signature.parameters:
        raise TypeError(
            f"{method.__qualname__}: @audited names a parameter '{name}' that the method does "
            f"not take. Its parameters are: {', '.join(signature.parameters)}."
        )


def _id_of(method: Callable[..., Any], result: object) -> uuid.UUID:
    """The created thing's id, for a method that had nothing to point at before it ran."""
    entity_id = getattr(result, "id", None)
    if not isinstance(entity_id, uuid.UUID):
        raise TypeError(
            f"{method.__qualname__}: @audited without a key takes the entity id from what the "
            f"method returns, and this returned {type(result).__name__} with no uuid id."
        )
    return entity_id


def _subjects(service: AuditedService, actor: Actor) -> AuditSubjects:
    from app.repositories.audit import AuditSubjectRepository

    return AuditSubjectRepository(service.session, actor.scope)


class AuditSubjects(Protocol):
    """The loader's shape, named here so `core` does not import `repositories` at module level."""

    async def snapshot(self, entity: str, entity_id: uuid.UUID) -> dict[str, object] | None: ...


def _changed(
    this: Mapping[str, object] | None, other: Mapping[str, object] | None
) -> dict[str, object] | None:
    """Only the columns that moved, from this side's point of view.

    A row carrying every column of both states would be a second copy of the table with no
    retention story — and the question somebody asks of the trail is *what changed*, not *what the
    row looked like*. A create or a delete keeps its whole side, because there the answer is
    everything.
    """
    if this is None:
        return None
    if other is None:
        return dict(this)
    changed = {key: value for key, value in this.items() if other.get(key) != value}
    return changed or None


def scrub(values: Mapping[str, object]) -> dict[str, object]:
    """Drop anything that looks like a credential, and make the rest JSON-safe.

    Exported because the same rule has to hold for a snapshot taken anywhere else — a service that
    builds its own dictionary for a row the decorator cannot produce still goes through here.
    """
    return {
        key: _jsonable(value)
        for key, value in values.items()
        if key not in _NOT_A_CHANGE and not any(word in key.lower() for word in _REDACTED)
    }


def _jsonable(value: object) -> object:
    """`Decimal` becomes a string and never a float (invariant 3): JSONB has only floats, and a
    price that round-trips through one is a price that has been quietly changed."""
    if isinstance(value, Decimal | uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if value is None or isinstance(value, str | int | bool | list | dict):
        return value
    return str(value)
