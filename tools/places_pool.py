"""Place-pool helpers for the ExperienceFinder vault.

Deterministic extraction of places from rendered Maps-list HTML and idempotent
upsert into a per-trip pool page `vault/wiki/itinerari/<trip>-luoghi.md`
(itinerari pages themselves live in the Travel node; this helper is shared
tooling migrated alongside destinazioni/esperienze/radar). Stdlib + PyYAML
only. Shared by the interactive /ingest path (HTML rendered via the
chrome-devtools MCP) and any tool that has the vault checked out.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

_LIST_NAME_COORDS_RE = re.compile(
    r'"([^"\\]{2,90})"[^"]{0,400}?!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)'
)


def extract_list_places_from_html(html: str) -> list[dict]:
    """Pull (name, lat, lng) triples from a rendered Maps-list page.

    Anchored on the stable '!3d<lat>!4d<lng>' marker preceded by a quoted name.
    Deduped by lowercased name. Never raises; returns [] when nothing matches."""
    seen: set[str] = set()
    out: list[dict] = []
    for m in _LIST_NAME_COORDS_RE.finditer(html):
        name = m.group(1).strip()
        key = name.lower()
        if not name or key in seen:
            continue
        try:
            lat, lng = float(m.group(2)), float(m.group(3))
        except ValueError:
            continue
        seen.add(key)
        out.append({"name": name, "lat": lat, "lng": lng})
    return out


def _dedup_keys(entry: dict) -> tuple[str, Optional[tuple[float, float]]]:
    name_key = str(entry.get("name", "")).strip().lower()
    lat, lng = entry.get("lat"), entry.get("lng")
    coord_key = None
    if lat is not None and lng is not None:
        coord_key = (round(float(lat), 4), round(float(lng), 4))
    return name_key, coord_key


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text). Body excludes the frontmatter block."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            body = text[end + 4:]
            if body.startswith("\n"):
                body = body[1:]
            return fm, body
    return {}, text


def _new_pool(trip_slug: str, title: Optional[str], today: str) -> dict:
    return {
        "type": "luoghi",
        "title": title or f"{trip_slug} — luoghi",
        "tags": [],
        "created": today,
        "updated": today,
        "sources": "",
        "coverage": "low",
        "itinerario": f"[[{trip_slug}]]",
        "places": [],
    }


def upsert_places(pool_path: str, entries: list[dict], *, trip_slug: str,
                  title: Optional[str] = None, today: Optional[str] = None) -> dict:
    """Idempotently add place entries to a pool page, creating it if missing.

    Dedup: an entry is skipped if its normalized name OR its (lat,lng) rounded to
    4 decimals already exists. Returns {added, skipped, total}."""
    today = today or date.today().isoformat()
    path = Path(pool_path)
    if path.exists():
        fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        if not fm:
            fm = _new_pool(trip_slug, title, today)
            body = ""
    else:
        fm = _new_pool(trip_slug, title, today)
        body = (f"# {fm['title']}\n\n> Pool di luoghi candidati per [[{trip_slug}]]. "
                f"Alimentato da /ingest, consumato da /pianifica.\n")
    places = fm.get("places") or []

    existing_names: set[str] = set()
    existing_coords: set = set()
    for p in places:
        nk, ck = _dedup_keys(p)
        if nk:
            existing_names.add(nk)
        if ck:
            existing_coords.add(ck)

    added = skipped = 0
    for e in entries:
        nk, ck = _dedup_keys(e)
        if (nk and nk in existing_names) or (ck and ck in existing_coords):
            skipped += 1
            continue
        places.append({
            "name": str(e.get("name", "")).strip(),
            "category": e.get("category", "altro"),
            "lat": e.get("lat"),
            "lng": e.get("lng"),
            "source": e.get("source", ""),
            "hours": e.get("hours"),
            "priority": e.get("priority", "nice"),
            "note": e.get("note", ""),
        })
        if nk:
            existing_names.add(nk)
        if ck:
            existing_coords.add(ck)
        added += 1

    fm["places"] = places
    if added:
        fm["updated"] = today
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip()
    new_text = "---\n" + front + "\n---\n\n" + body.lstrip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return {"added": added, "skipped": skipped, "total": len(places)}


def _main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Upsert luoghi nel place pool di un viaggio.")
    ap.add_argument("pool", help="path al <trip>-luoghi.md")
    ap.add_argument("--trip", required=True, help="slug del viaggio (per [[link]] e titolo)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-html", help="file HTML (lista Maps renderizzata) da cui estrarre i luoghi")
    src.add_argument("--places-json", help="JSON: lista di {name,lat,lng,category?,source?}")
    ap.add_argument("--source", default="", help="source da assegnare ai luoghi estratti (es. URL lista)")
    ap.add_argument("--title", default=None)
    args = ap.parse_args(argv)

    if args.from_html:
        html = Path(args.from_html).read_text(encoding="utf-8", errors="replace")
        entries = extract_list_places_from_html(html)
        for e in entries:
            e["source"] = args.source
    else:
        entries = json.loads(args.places_json)

    summary = upsert_places(args.pool, entries, trip_slug=args.trip, title=args.title)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
