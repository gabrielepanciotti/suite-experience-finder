import json
from pathlib import Path

from tools.places_pool import extract_list_places_from_html, upsert_places


def test_extract_names_and_coords():
    html = 'x "Belem" y !3d38.6975!4d-9.2034 z "Castelo" w !3d38.7139!4d-9.1335'
    got = extract_list_places_from_html(html)
    assert [p["name"] for p in got] == ["Belem", "Castelo"]
    assert abs(got[0]["lat"] - 38.6975) < 1e-9
    assert abs(got[0]["lng"] + 9.2034) < 1e-9


def test_extract_dedup_by_name():
    html = '"AB" !3d1.0!4d2.0 "AB" !3d1.0!4d2.0'
    assert len(extract_list_places_from_html(html)) == 1


def test_extract_empty():
    assert extract_list_places_from_html("nothing") == []


def test_upsert_creates_pool(tmp_path):
    pool = tmp_path / "lis-luoghi.md"
    res = upsert_places(str(pool), [{"name": "Belem", "lat": 38.69, "lng": -9.2, "source": "u"}],
                        trip_slug="lis", today="2026-06-15")
    assert pool.exists()
    assert res == {"added": 1, "skipped": 0, "total": 1}
    txt = pool.read_text(encoding="utf-8")
    assert "type: luoghi" in txt and "Belem" in txt and "[[lis]]" in txt


def test_upsert_is_idempotent(tmp_path):
    pool = tmp_path / "lis-luoghi.md"
    e = [{"name": "Belem", "lat": 38.69, "lng": -9.2}]
    upsert_places(str(pool), e, trip_slug="lis", today="2026-06-15")
    res2 = upsert_places(str(pool), e, trip_slug="lis", today="2026-06-15")
    assert res2["added"] == 0 and res2["skipped"] == 1 and res2["total"] == 1


def test_upsert_dedup_by_coords(tmp_path):
    pool = tmp_path / "lis-luoghi.md"
    upsert_places(str(pool), [{"name": "Belem", "lat": 38.6975, "lng": -9.2034}], trip_slug="lis", today="2026-06-15")
    res = upsert_places(str(pool), [{"name": "Pasteis", "lat": 38.69751, "lng": -9.20341}], trip_slug="lis", today="2026-06-15")
    assert res["added"] == 0 and res["skipped"] == 1


def test_upsert_preserves_body(tmp_path):
    pool = tmp_path / "lis-luoghi.md"
    pool.write_text('---\ntype: luoghi\nitinerario: "[[lis]]"\nplaces: []\n---\n\n# Lisbona\n\nNota mia.\n', encoding="utf-8")
    upsert_places(str(pool), [{"name": "X", "lat": 1.0, "lng": 2.0}], trip_slug="lis", today="2026-06-15")
    txt = pool.read_text(encoding="utf-8")
    assert "Nota mia." in txt and "X" in txt
