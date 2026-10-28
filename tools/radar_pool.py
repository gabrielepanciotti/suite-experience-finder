"""Radar-pool helpers for the ExperienceFinder vault.

Idempotent upsert of saved-reel spots/tips into a per-region radar page
`vault/wiki/radar/<regione>.md`. Twin of places_pool.py — stdlib + PyYAML only.
Fed by /reels (after Gonzalo synthesizes caption+transcript), read by /radar.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import yaml


def _dedup_key(entry: dict) -> str:
    """Normalized name key. '' when absent.

    Dedup is name-only (within a region file): a single reel can describe several
    distinct places ('3 posti in Toscana'), so the reel_url must NOT collapse them."""
    return str(entry.get("name", "")).strip().lower()


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            body = text[end + 4:]
            if body.startswith("\n"):
                body = body[1:]
            return fm, body
    return {}, text


def _new_radar(regione: str, title: Optional[str], today: str) -> dict:
    return {
        "type": "radar",
        "title": title or f"{regione} — radar",
        "regione": regione,
        "tags": [],
        "created": today,
        "updated": today,
        "coverage": "low",
        "spots": [],
    }


def upsert_spots(radar_path: str, entries: list[dict], *, regione: str,
                 title: Optional[str] = None, today: Optional[str] = None) -> dict:
    """Idempotently add spot/tip entries to a region radar, creating it if missing.

    Dedup: an entry is skipped if its normalized name already exists in the file
    (name-only — a multi-place reel yields several distinct spots that share a
    reel_url and must all be kept). Returns {added, skipped, total}."""
    today = today or date.today().isoformat()
    path = Path(radar_path)
    if path.exists():
        fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        if not fm:
            fm = _new_radar(regione, title, today)
            body = ""
    else:
        fm = _new_radar(regione, title, today)
        body = (f"# {fm['title']}\n\n> Spot e tip salvati per la regione. "
                f"Alimentato da /reels, consultato con /radar.\n")
    spots = fm.get("spots") or []

    existing_names: set[str] = set()
    for s in spots:
        nk = _dedup_key(s)
        if nk:
            existing_names.add(nk)

    added = skipped = 0
    for e in entries:
        nk = _dedup_key(e)
        if nk and nk in existing_names:
            skipped += 1
            continue
        spots.append({
            "name": str(e.get("name", "")).strip(),
            "kind": e.get("kind", "spot"),
            "zona": e.get("zona", regione),
            "category": e.get("category", "altro"),
            "note": e.get("note", ""),
            "lat": e.get("lat"),
            "lng": e.get("lng"),
            "reel_url": e.get("reel_url", ""),
            "source": e.get("source", "instagram-saved"),
            "added": today,
        })
        if nk:
            existing_names.add(nk)
        added += 1

    fm["spots"] = spots
    if added:
        fm["updated"] = today
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip()
    new_text = "---\n" + front + "\n---\n\n" + body.lstrip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return {"added": added, "skipped": skipped, "total": len(spots)}


def _main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Upsert spot/tip nel radar di una regione.")
    ap.add_argument("radar", help="path al vault/wiki/radar/<regione>.md")
    ap.add_argument("--regione", required=True, help="slug della regione")
    ap.add_argument("--spots-json", required=True,
                    help="JSON: lista di {name,kind,category,note,lat,lng,reel_url,source}")
    ap.add_argument("--title", default=None)
    args = ap.parse_args(argv)
    entries = json.loads(args.spots_json)
    summary = upsert_spots(args.radar, entries, regione=args.regione, title=args.title)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
