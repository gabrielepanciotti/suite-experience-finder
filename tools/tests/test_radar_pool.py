from tools.radar_pool import upsert_spots


def _spot(**kw):
    base = {"name": "Rocca Calascio", "kind": "spot", "category": "borgo",
            "note": "vista", "lat": 42.34, "lng": 13.7,
            "reel_url": "https://www.instagram.com/reel/AAA/", "source": "ig"}
    base.update(kw)
    return base


def test_upsert_creates_radar(tmp_path):
    radar = tmp_path / "abruzzo.md"
    res = upsert_spots(str(radar), [_spot()], regione="abruzzo", today="2026-06-18")
    assert radar.exists()
    assert res == {"added": 1, "skipped": 0, "total": 1}
    txt = radar.read_text(encoding="utf-8")
    assert "type: radar" in txt and "Rocca Calascio" in txt and "regione: abruzzo" in txt


def test_upsert_keeps_distinct_spots_from_same_reel(tmp_path):
    # un reel "3 posti in Toscana" produce più spot distinti che condividono reel_url:
    # vanno TENUTI tutti (la dedup è per nome, non per reel_url).
    radar = tmp_path / "abruzzo.md"
    upsert_spots(str(radar), [_spot()], regione="abruzzo", today="2026-06-18")
    res = upsert_spots(str(radar), [_spot(name="Altro nome")], regione="abruzzo",
                       today="2026-06-18")
    assert res["added"] == 1 and res["skipped"] == 0 and res["total"] == 2


def test_upsert_dedup_by_name(tmp_path):
    radar = tmp_path / "abruzzo.md"
    upsert_spots(str(radar), [_spot()], regione="abruzzo", today="2026-06-18")
    res = upsert_spots(str(radar), [_spot(reel_url="https://www.instagram.com/reel/BBB/")],
                       regione="abruzzo", today="2026-06-18")
    assert res["added"] == 0 and res["skipped"] == 1


def test_upsert_tip_without_coords(tmp_path):
    radar = tmp_path / "abruzzo.md"
    res = upsert_spots(str(radar), [_spot(name="Arrosticini ovunque", kind="tip",
                       category="food", lat=None, lng=None)],
                       regione="abruzzo", today="2026-06-18")
    assert res["added"] == 1
    txt = radar.read_text(encoding="utf-8")
    assert "kind: tip" in txt and "Arrosticini" in txt


def test_upsert_preserves_body_and_accents(tmp_path):
    radar = tmp_path / "abruzzo.md"
    radar.write_text('---\ntype: radar\nregione: abruzzo\nspots: []\n---\n\n# Abruzzo\n\nNota mia.\n',
                     encoding="utf-8")
    upsert_spots(str(radar), [_spot(name="Caffè è perché")], regione="abruzzo",
                 today="2026-06-18")
    txt = radar.read_text(encoding="utf-8")
    assert "Nota mia." in txt and "Caffè è perché" in txt
