"""Reel-ingest helpers for the ExperienceFinder vault.

Layer 1 of the saved-reel pipeline: a saved IG collection is expanded into reel
URLs via the web private API (cookies-authenticated — yt-dlp has no extractor
for saved collections), then yt-dlp pulls caption + audio per reel and
faster-whisper transcribes the audio. Produces a raw bundle
{url, author, caption, transcript, duration} that Gonzalo later synthesizes into
radar spots/tips via radar_pool.py.

Pure helpers (parse/build/slug/transcribe) are unit-tested; the yt-dlp/whisper
integration is best-effort and smoke-tested manually.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib import util as importlib_util
from pathlib import Path
from shutil import which
from typing import Optional

YTDLP_TIMEOUT = 300
_MODEL_CACHE: dict = {}
_COOKIE_COPY: dict = {}


def _load_model(model_size: str):
    """Lazily load and cache a faster-whisper model (CPU, int8)."""
    if model_size not in _MODEL_CACHE:
        from faster_whisper import WhisperModel
        _MODEL_CACHE[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[model_size]


def _ytdlp_command() -> Optional[list[str]]:
    if importlib_util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    binary = which("yt-dlp")
    return [binary] if binary else None


def _ytdlp_cookies(cookies: Optional[str]) -> list[str]:
    """--cookies args for yt-dlp, copied to a writable temp file.

    yt-dlp rewrites the cookie jar after each use; a read-only cookies file (the
    bot mounts /secrets read-only) makes it raise. Copy once, reuse the temp."""
    if not cookies:
        return []
    if cookies not in _COOKIE_COPY:
        import shutil
        import tempfile
        try:
            fd, tmp = tempfile.mkstemp(prefix="ig_cookies_", suffix=".txt")
            os.close(fd)
            shutil.copyfile(cookies, tmp)
            _COOKIE_COPY[cookies] = tmp
        except OSError:
            _COOKIE_COPY[cookies] = cookies  # fall back to the original path
    return ["--cookies", _COOKIE_COPY[cookies]]

_REEL_ID_RE = re.compile(r"/(?:reel|reels|p|tv)/([^/?#]+)")
_COLLECTION_ID_RE = re.compile(r"/saved/[^/]+/(\d+)")
IG_APP_ID = "936619743392459"  # public web app id used by instagram.com


def parse_reel_metadata(raw: dict) -> dict:
    """Extract the fields we keep from a yt-dlp --dump-json dict."""
    return {
        "url": raw.get("webpage_url") or raw.get("url") or "",
        "author": raw.get("uploader") or raw.get("uploader_id") or "",
        "caption": (raw.get("description") or "").strip(),
        "duration": raw.get("duration"),
    }


def build_bundle(meta: dict, transcript: str) -> dict:
    """Assemble the raw bundle from metadata + transcript."""
    return {
        "url": meta.get("url", ""),
        "author": meta.get("author", ""),
        "caption": meta.get("caption", ""),
        "transcript": transcript.strip(),
        "duration": meta.get("duration"),
    }


def slug_for_reel(url: str) -> str:
    """Filesystem-safe id for a reel: the IG reel id when present, else a sanitized url."""
    m = _REEL_ID_RE.search(url or "")
    if m:
        return m.group(1)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", (url or "reel")).strip("-")
    return safe or "reel"


def transcribe_audio(audio_path: str, *, model=None, model_size: str = "small") -> str:
    """Transcribe an audio file with faster-whisper.

    `model` is injectable for testing; in production a WhisperModel is lazily
    loaded. Returns the joined transcript text (empty string on no speech)."""
    if model is None:
        model = _load_model(model_size)
    segments, _info = model.transcribe(str(audio_path))
    return " ".join(seg.text.strip() for seg in segments).strip()


def _collection_id_from_url(collection: str) -> Optional[str]:
    """Numeric collection id from a saved-collection URL, or a bare id passed through."""
    s = (collection or "").strip()
    if s.isdigit():
        return s
    m = _COLLECTION_ID_RE.search(s)
    return m.group(1) if m else None


def _cookie_header_from_file(cookies_path: str) -> tuple[str, str]:
    """Build a Cookie header + csrftoken from an exported Netscape cookies.txt."""
    from http.cookiejar import MozillaCookieJar
    jar = MozillaCookieJar()
    jar.load(cookies_path, ignore_discard=True, ignore_expires=True)
    pairs = {c.name: c.value for c in jar if "instagram.com" in (c.domain or "")}
    header = "; ".join(f"{k}={v}" for k, v in pairs.items())
    return header, pairs.get("csrftoken", "")


def _items_to_reel_urls(items: list[dict]) -> list[str]:
    """Map IG feed items to canonical reel/post URLs (deduped, order preserved)."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        media = it.get("media", it)
        code = media.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        kind = "reel" if media.get("media_type") == 2 else "p"
        out.append(f"https://www.instagram.com/{kind}/{code}/")
    return out


def list_reel_urls(collection: str, *, cookies: Optional[str],
                   warnings: list[str]) -> list[str]:
    """Expand a saved IG collection into individual reel/post URLs.

    Uses the web private API (yt-dlp has no extractor for saved collections);
    `collection` is the saved-collection URL or its numeric id. Best-effort:
    returns [] (with a warning) on any failure."""
    coll_id = _collection_id_from_url(collection)
    if not coll_id:
        warnings.append(f"id collezione non estraibile da '{collection}'")
        return []
    if not cookies:
        warnings.append("le collezioni 'salvati' sono private: serve --cookies")
        return []
    try:
        import httpx
    except ImportError:
        warnings.append("httpx non disponibile; impossibile leggere la collezione")
        return []
    try:
        cookie_header, csrf = _cookie_header_from_file(cookies)
    except OSError as exc:
        warnings.append(f"cookies illeggibili {cookies}: {exc}")
        return []
    headers = {
        "x-ig-app-id": IG_APP_ID,
        "x-csrftoken": csrf,
        "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        "cookie": cookie_header,
        "referer": "https://www.instagram.com/",
        "x-requested-with": "XMLHttpRequest",
    }
    items: list[dict] = []
    max_id = ""
    api = f"https://www.instagram.com/api/v1/feed/collection/{coll_id}/posts/"
    try:
        with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
            for _ in range(50):  # hard page cap
                resp = client.get(api, params={"max_id": max_id} if max_id else None)
                if resp.status_code != 200:
                    warnings.append(f"IG API HTTP {resp.status_code} sulla collezione {coll_id}")
                    break
                data = resp.json()
                items.extend(data.get("items", []))
                if not data.get("more_available"):
                    break
                max_id = data.get("next_max_id") or ""
                if not max_id:
                    break
    except (httpx.HTTPError, ValueError) as exc:
        warnings.append(f"IG API fallita: {exc.__class__.__name__}: {exc}")
    return _items_to_reel_urls(items)


def fetch_reel_raw(url: str, audio_dir: Path, *, cookies: Optional[str],
                   warnings: list[str]) -> tuple[dict, Optional[Path]]:
    """Download audio + dump metadata for one reel. Returns (raw_json, audio_path).

    raw_json is {} and audio_path is None on failure (warning appended)."""
    base = _ytdlp_command()
    if base is None:
        warnings.append("yt-dlp non disponibile; reel saltato")
        return {}, None
    try:
        audio_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        warnings.append(f"cartella audio non creabile {audio_dir}: {exc}")
        return {}, None
    out_tmpl = str(audio_dir / "%(id)s.%(ext)s")
    cmd = base + _ytdlp_cookies(cookies) + [
        "--no-playlist", "--no-progress", "-x", "--audio-format", "mp3",
        "--write-info-json", "--print", "after_move:filepath",
        "-o", out_tmpl, url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=YTDLP_TIMEOUT, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        warnings.append(f"yt-dlp reel fallito: {exc.__class__.__name__}: {exc}")
        return {}, None
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        warnings.append(f"yt-dlp reel rc={proc.returncode}: {tail[-1] if tail else 'no stderr'}")
        return {}, None
    audio_path = next((Path(ln.strip()) for ln in proc.stdout.splitlines()
                       if ln.strip() and Path(ln.strip()).exists()), None)
    raw = {}
    if audio_path is not None:
        info = audio_path.with_suffix(".info.json")
        if info.exists():
            try:
                raw = json.loads(info.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                warnings.append(f"info.json illeggibile per {url}: {exc}")
    return raw, audio_path


def ingest_reel(url: str, audio_dir: Path, *, cookies: Optional[str],
                model_size: str = "small") -> dict:
    """Full single-reel pipeline → bundle with a 'warnings' list."""
    warnings: list[str] = []
    raw, audio_path = fetch_reel_raw(url, audio_dir, cookies=cookies, warnings=warnings)
    meta = parse_reel_metadata(raw) if raw else {"url": url, "author": "",
                                                 "caption": "", "duration": None}
    if not meta.get("url"):
        meta["url"] = url
    transcript = ""
    if audio_path is not None:
        try:
            transcript = transcribe_audio(str(audio_path), model_size=model_size)
        except Exception as exc:  # whisper/ffmpeg runtime errors — keep batch alive
            warnings.append(f"trascrizione fallita per {url}: {exc.__class__.__name__}: {exc}")
    bundle = build_bundle(meta, transcript)
    bundle["warnings"] = warnings
    return bundle


def ingest_urls(urls: list[str], audio_dir: Path, *, cookies: Optional[str],
                model_size: str = "small") -> list[dict]:
    """Ingest a list of reel URLs into bundles. One failure never aborts the batch."""
    return [ingest_reel(u, audio_dir, cookies=cookies, model_size=model_size) for u in urls]


def _main(argv=None) -> int:
    import argparse
    import datetime
    try:  # Windows consoles default to cp1252 and choke on emoji in captions
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Ingest reel IG salvati (caption + audio) → bundle JSON grezzi.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--collection", help="URL della collezione 'salvati' (privata) da espandere")
    src.add_argument("--urls", nargs="+", help="lista di URL di reel")
    ap.add_argument("--cookies", default=None,
                    help="path a cookies.txt (login IG). Senza, le collezioni private falliscono.")
    ap.add_argument("--audio-dir", default="vault/raw/media",
                    help="cartella dove yt-dlp scarica l'audio")
    ap.add_argument("--out-dir", default="vault/raw/reels",
                    help="cartella dove salvare i bundle JSON per reel")
    ap.add_argument("--model", default="small", help="dimensione modello faster-whisper")
    args = ap.parse_args(argv)

    warnings: list[str] = []
    audio_dir = Path(args.audio_dir)
    if args.collection:
        urls = list_reel_urls(args.collection, cookies=args.cookies, warnings=warnings)
    else:
        urls = args.urls

    bundles = ingest_urls(urls, audio_dir, cookies=args.cookies, model_size=args.model)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    for b in bundles:
        fname = f"{today}-{slug_for_reel(b['url'])}.json"
        (out_dir / fname).write_text(json.dumps(b, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print(json.dumps({"reels": len(bundles), "warnings": warnings,
                      "bundles": bundles}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
