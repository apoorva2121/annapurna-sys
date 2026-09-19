"""The URL behind a table's QR code, for testing before anything is printed.

A guest reaches this product by scanning a code on the table, which is nothing more than a link:

    <base>/guest.html?t=<guest_slug>

`restaurant_table.guest_slug` is 128 bits of randomness and is unique **across the whole product**,
because the slug is what *determines* the tenant — there is no restaurant id in the URL and there
must not be one. So a link printed here is the real thing, not a stand-in, and it should be treated
like one: anybody holding it can read that restaurant's menu and that table's live bill.

Usage:

    # Local, with `make dev` running (vite serves the guest bundle on 5173)
    python scripts/guest_links.py

    # Staging or production, where one origin serves both (ADR 0005)
    python scripts/guest_links.py --base-url https://<host>

    # A page you can open and scan from a phone
    python scripts/guest_links.py --base-url https://<host> --html guest-qr.html

`--html` writes a self-contained page that draws a QR for each table. The QR is rendered in the
browser rather than here, because no QR library is installed in this project's environment and
adding a dependency to print a test page is the wrong trade — the page names the library and the
version it loads so it is auditable.

**This reads the database directly** and takes `DATABASE_URL` from the environment, the same way
`app.bootstrap` does. Run it against whichever database you are testing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.models.setup import DiningArea, RestaurantTable
from app.models.tenancy import Restaurant

# Vite's dev server, which is what `make dev` puts the guest bundle behind. In staging and
# production one origin serves both bundles and the API (ADR 0005), so --base-url is the host.
DEFAULT_BASE = "http://localhost:5173"


async def _rows(database_url: str) -> list[tuple[str, str, str, str]]:
    engine = create_async_engine(database_url)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(
                    Restaurant.name,
                    DiningArea.name,
                    RestaurantTable.code,
                    RestaurantTable.guest_slug,
                )
                .join(RestaurantTable, RestaurantTable.restaurant_id == Restaurant.id)
                .join(DiningArea, DiningArea.id == RestaurantTable.dining_area_id)
                .where(RestaurantTable.is_active.is_(True))
                .order_by(Restaurant.name, DiningArea.seq, RestaurantTable.code)
            )
            return [tuple(row) for row in result.all()]  # type: ignore[misc]
    finally:
        await engine.dispose()


def _page(links: list[dict[str, str]]) -> str:
    """One card per table, each with a QR drawn in the browser.

    `qrcode-generator` 1.4.4 from cdnjs, pinned **with a Subresource Integrity hash computed from
    the bytes actually served** rather than copied from a listing. A compromised CDN then breaks
    the page instead of silently rewriting the links it draws — which is the whole risk on a page
    whose entire content is live guest tokens.

    Nothing about the page is secret; the links on it are. It says so at the top rather than
    trusting whoever opens it to work that out.
    """
    payload = json.dumps(links)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Table QR codes — test only</title>
<style>
  body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0; padding: 24px; background: #faf8f5; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .warn {{ background: #fff4e5; border: 1px solid #e0b070; padding: 12px 16px;
           border-radius: 6px; margin: 16px 0 24px; max-width: 46rem; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
  .card {{ background: #fff; border: 1px solid #e4ded6; border-radius: 8px; padding: 16px;
           width: 220px; }}
  .code {{ font-weight: 600; }}
  .where {{ color: #6b625a; font-size: 14px; }}
  .url {{ font-size: 11px; word-break: break-all; color: #6b625a; margin-top: 8px; }}
  canvas, img {{ display: block; margin: 12px auto 0; }}
</style>
</head>
<body>
<h1>Table QR codes</h1>
<div class="warn">
  <strong>These are live links, not samples.</strong> Each one opens that table's menu and its
  current bill, with no password — that is how a QR on a table is meant to work. Treat this page
  the way you would treat the printed codes: do not share it, and regenerate the slugs if it
  leaks.
</div>
<div class="grid" id="grid"></div>
<!-- Pinned with Subresource Integrity: the hash was computed from the bytes actually served,
     not copied from anywhere. If cdnjs is ever compromised the browser refuses the script and
     the page draws nothing, which is the failure you want on a page that renders live links. -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js"
        integrity="sha384-mZT2gIty7ZDdOGkxfP6joZcYdMW1Jvj9dRlfpTmaJAKKXTqzygtB22k7FLe+KZC1"
        crossorigin="anonymous"></script>
<script>
  const links = {payload};
  const grid = document.getElementById('grid');
  for (const link of links) {{
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML =
      '<div class="code"></div><div class="where"></div><div class="qr"></div>' +
      '<div class="url"></div>';
    card.querySelector('.code').textContent = link.table;
    card.querySelector('.where').textContent = link.restaurant + ' · ' + link.area;
    card.querySelector('.url').textContent = link.url;
    // Level M correction: a table tent gets scuffed, and M reads through a fingerprint.
    const qr = qrcode(0, 'M');
    qr.addData(link.url);
    qr.make();
    card.querySelector('.qr').innerHTML = qr.createImgTag(5, 8);
    grid.appendChild(card);
  }}
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE, help=f"default {DEFAULT_BASE}")
    parser.add_argument("--html", help="also write a page of scannable QR codes here")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="defaults to $DATABASE_URL",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("Set DATABASE_URL, or pass --database-url.", file=sys.stderr)
        return 2

    rows = asyncio.run(_rows(args.database_url))
    if not rows:
        print("No active tables. Run `make seed` first.", file=sys.stderr)
        return 1

    base = args.base_url.rstrip("/")
    links = [
        {
            "restaurant": restaurant,
            "area": area,
            "table": code,
            "url": f"{base}/guest.html?t={slug}",
        }
        for restaurant, area, code, slug in rows
    ]

    width = max(len(f"{link['restaurant']} · {link['area']} · {link['table']}") for link in links)
    for link in links:
        label = f"{link['restaurant']} · {link['area']} · {link['table']}"
        print(f"{label.ljust(width)}  {link['url']}")

    if args.html:
        Path(args.html).write_text(_page(links), encoding="utf-8")
        print(f"\nWrote {args.html} — open it and scan from a phone.", file=sys.stderr)

    print(
        "\nThese are live guest links: each opens that table's menu and its current bill with no\n"
        "password. That is the design (ADR 0009), and it is also why the slug is 128 bits.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
