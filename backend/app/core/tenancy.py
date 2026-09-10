"""The tenant scope, and the only legitimate way to build one.

Every repository takes a `TenantScope`. It is a required positional argument with no default, so
the failure mode "someone forgot to scope this query" is a `TypeError` at construction rather than
a customer reading another customer's data (CLAUDE.md invariant 1).

The scope is derived from the verified access token and never from anything the client can choose
freely — a `restaurant_id` accepted from a query parameter or a request body would make the whole
mechanism decorative.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Who is asking, and where.

    Two levels because the threat model has two attackers. The **organization** is the hard tenant
    boundary: another organization's rows must be unreachable, full stop. The **restaurant** is the
    boundary inside one organization, because "a manager reads another branch's staff" is its own
    entry in the M01 threat table.

    Frozen, so nothing can widen a scope halfway through a request.
    """

    organization_id: uuid.UUID
    restaurant_id: uuid.UUID
