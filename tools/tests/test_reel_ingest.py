from pathlib import Path

from tools.reel_ingest import (
    parse_reel_metadata, build_bundle, slug_for_reel, transcribe_audio,
    _collection_id_from_url, _items_to_reel_urls, _ytdlp_cookies,
)


def test_parse_reel_metadata():
    raw = {"webpage_url": "https://www.instagram.com/reel/ABC/",
           "uploader": "alice", "description": "Borgo top in Abruzzo",
           "duration": 42.0, "id": "ABC"}
    meta = parse_reel_metadata(raw)
    assert meta["url"] == "https://www.instagram.com/reel/ABC/"
    assert meta["author"] == "alice"
    assert meta["caption"] == "Borgo top in Abruzzo"
    assert meta["duration"] == 42.0


def test_parse_reel_metadata_missing_fields():
    meta = parse_reel_metadata({"id": "X"})
    assert meta["caption"] == "" and meta["author"] == "" and meta["url"] == ""


def test_build_bundle():
    meta = {"url": "u", "author": "a", "caption": "c", "duration": 10.0}
    b = build_bundle(meta, "trascrizione qui")
    assert b == {"url": "u", "author": "a", "caption": "c",
                 "transcript": "trascrizione qui", "duration": 10.0}


def test_slug_for_reel_from_url():
    assert slug_for_reel("https://www.instagram.com/reel/AbC123/") == "AbC123"


def test_slug_for_reel_from_post_url():
    assert slug_for_reel("https://www.instagram.com/p/DZu71l7jKb7/") == "DZu71l7jKb7"


def test_slug_for_reel_fallback():
    # senza /reel/<id>/ ripiega su una stringa non vuota e filesystem-safe
    s = slug_for_reel("https://example.com/x?y=1")
    assert s and "/" not in s and "?" not in s


def test_collection_id_from_url():
    url = "https://www.instagram.com/alice/saved/viaggi/18094131751387654/"
    assert _collection_id_from_url(url) == "18094131751387654"


def test_collection_id_from_bare_id():
    assert _collection_id_from_url("18094131751387654") == "18094131751387654"


def test_collection_id_none_when_absent():
    assert _collection_id_from_url("https://www.instagram.com/reel/ABC/") is None


def test_ytdlp_cookies_none():
    assert _ytdlp_cookies(None) == []


def test_ytdlp_cookies_copies_to_writable_temp(tmp_path):
    src = tmp_path / "cookies.txt"
    src.write_text("# Netscape\nfoo\tbar\n", encoding="utf-8")
    args = _ytdlp_cookies(str(src))
    assert args[0] == "--cookies"
    copy = Path(args[1])
    assert copy.exists() and copy != src
    assert copy.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_items_to_reel_urls_maps_kind_and_dedups():
    items = [
        {"media": {"code": "AAA", "media_type": 2}},   # reel
        {"media": {"code": "BBB", "media_type": 1}},   # post
        {"media": {"code": "AAA", "media_type": 2}},   # dup
        {"media": {"media_type": 2}},                   # no code → skip
    ]
    assert _items_to_reel_urls(items) == [
        "https://www.instagram.com/reel/AAA/",
        "https://www.instagram.com/p/BBB/",
    ]


def test_transcribe_audio_with_fake_model():
    class _Seg:
        def __init__(self, text): self.text = text

    class _FakeModel:
        def transcribe(self, path, **kw):
            return iter([_Seg("Ciao "), _Seg(" mondo")]), {"language": "it"}

    text = transcribe_audio("/tmp/x.mp3", model=_FakeModel())
    assert text == "Ciao mondo"
