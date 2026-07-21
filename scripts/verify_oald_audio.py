"""
Verify and repair OALD audio URLs in data/oald/words.{json,csv}.

Some OALD pages embed stale .ogg paths (404) while a sibling .mp3 or a
lower-index file (__us_1) still works. This script HEADs every unique URL
and rewrites dead ones to the first working fallback.

Usage:
  python scripts/verify_oald_audio.py
  python scripts/verify_oald_audio.py --workers 24
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "oald"
JSON_PATH = OUT_DIR / "words.json"
CSV_PATH = OUT_DIR / "words.csv"
REPORT_PATH = OUT_DIR / "audio_link_check.json"

SCHEMA_COLS = [
    "word_us",
    "word_gb",
    "lexical_category",
    "cefr",
    "definition_url_oxford",
    "definition_url_cambridge",
    "ipa_us",
    "ipa_gb",
    "definition",
    "example",
    "audio_source_us",
    "audio_source_gb",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Referer": "https://www.oxfordlearnersdictionaries.com/",
}


def url_ok(url: str, timeout: float = 15.0) -> bool:
    req = urllib.request.Request(url, method="HEAD", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 206)
    except urllib.error.HTTPError as e:
        if e.code in (403, 405, 501):
            try:
                req2 = urllib.request.Request(
                    url, headers={**HEADERS, "Range": "bytes=0-1"}
                )
                with urllib.request.urlopen(req2, timeout=timeout) as resp:
                    return resp.status in (200, 206)
            except Exception:  # noqa: BLE001
                return False
        return False
    except Exception:  # noqa: BLE001
        return False


def fallback_candidates(url: str) -> list[str]:
    """Generate alternate URLs when the primary OALD audio path is dead.

    Preference: same container/format with a lower index (__us_1), then the
    sibling mp3/ogg on the other CDN path.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    add(url)

    m = re.search(r"__(us|gb)_(\d+)(_rr)?\.(ogg|mp3)$", url)

    def with_index(u: str, geo: str, i: int, rr: str, ext: str) -> str:
        return re.sub(
            r"__(us|gb)_\d+(_rr)?\.(ogg|mp3)$",
            f"__{geo}_{i}{rr}.{ext}",
            u,
        )

    def sibling_format(u: str) -> str | None:
        if "/us_pron_ogg/" in u and u.endswith(".ogg"):
            return u.replace("/us_pron_ogg/", "/us_pron/")[:-4] + ".mp3"
        if "/uk_pron_ogg/" in u and u.endswith(".ogg"):
            return u.replace("/uk_pron_ogg/", "/uk_pron/")[:-4] + ".mp3"
        if "/us_pron/" in u and u.endswith(".mp3"):
            return u.replace("/us_pron/", "/us_pron_ogg/")[:-4] + ".ogg"
        if "/uk_pron/" in u and u.endswith(".mp3"):
            return u.replace("/uk_pron/", "/uk_pron_ogg/")[:-4] + ".ogg"
        return None

    if m:
        geo, n, rr, ext = m.group(1), int(m.group(2)), m.group(3) or "", m.group(4)
        # Prefer lower indices in the same format first (__us_3.ogg → __us_1.ogg)
        for i in range(1, n):
            for rr_opt in ((rr,) if rr else ("", "_rr")):
                add(with_index(url, geo, i, rr_opt, ext))

    # Then sibling container (ogg ↔ mp3) for original + lower indices
    for base in list(out):
        sib = sibling_format(base)
        if sib:
            add(sib)

    return out


def resolve_url_simple(url: str, alive_cache: dict[str, bool]) -> str | None:
    for cand in fallback_candidates(url):
        if cand not in alive_cache:
            alive_cache[cand] = url_ok(cand)
        if alive_cache[cand]:
            return cand
    return None


def sanitize_list(urls: list[str], alive_cache: dict[str, bool]) -> tuple[list[str], list[dict]]:
    """Apply user rules for dead audio in one source block (us or gb).

    - If the block still has any living URL: drop dead ones only.
    - If every URL in the block is dead (typically a single dead link):
      replace each with the first living fallback (__us_1 / sibling mp3, …).
    """
    if not urls:
        return [], []

    for u in urls:
        if u not in alive_cache:
            alive_cache[u] = url_ok(u)

    living = [u for u in urls if alive_cache.get(u)]
    dead = [u for u in urls if not alive_cache.get(u)]
    changes: list[dict] = []

    if not dead:
        return list(urls), []

    if living:
        for u in dead:
            changes.append({"from": u, "to": None, "status": "removed"})
        # preserve original order of living URLs
        return living, changes

    # Entire block dead — replace with living fallbacks
    repaired: list[str] = []
    seen: set[str] = set()
    for u in urls:
        fixed = resolve_url_simple(u, alive_cache)
        if fixed is None:
            changes.append({"from": u, "to": None, "status": "unrecoverable"})
            continue
        if fixed != u:
            changes.append({"from": u, "to": fixed, "status": "replaced"})
        else:
            changes.append({"from": u, "to": fixed, "status": "kept"})
        if fixed not in seen:
            seen.add(fixed)
            repaired.append(fixed)
    return repaired, changes


def write_outputs(records: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA_COLS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = {k: r[k] for k in SCHEMA_COLS}
            for list_key in (
                "ipa_us",
                "ipa_gb",
                "audio_source_us",
                "audio_source_gb",
            ):
                row[list_key] = json.dumps(row[list_key], ensure_ascii=False)
            w.writerow(row)
    clean = [{k: r[k] for k in SCHEMA_COLS} for r in records]
    JSON_PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument(
        "--check-only",
        action="store_true",
        help="Do not rewrite files; only report",
    )
    args = ap.parse_args()

    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    all_urls: set[str] = set()
    for r in records:
        for key in ("audio_source_us", "audio_source_gb"):
            all_urls.update(r.get(key) or [])

    print(f"unique audio urls: {len(all_urls)}", flush=True)
    alive_cache: dict[str, bool] = {}
    lock = Lock()
    done = 0
    t0 = time.time()

    def check(u: str) -> tuple[str, bool]:
        return u, url_ok(u)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(check, u) for u in sorted(all_urls)]
        for fut in as_completed(futs):
            u, ok = fut.result()
            with lock:
                alive_cache[u] = ok
                done += 1
                if done % 500 == 0 or done == len(all_urls):
                    bad_n = sum(1 for v in alive_cache.values() if not v)
                    print(
                        f"checked {done}/{len(all_urls)} dead={bad_n} "
                        f"({time.time() - t0:.0f}s)",
                        flush=True,
                    )

    dead_primary = sorted(u for u, ok in alive_cache.items() if not ok)
    print(f"primary dead: {len(dead_primary)}", flush=True)

    all_changes: list[dict] = []
    empty_after: list[dict] = []
    n_repaired_entries = 0

    for r in records:
        entry_changed = False
        for key in ("audio_source_us", "audio_source_gb"):
            original = list(r.get(key) or [])
            fixed, changes = sanitize_list(original, alive_cache)
            if changes:
                all_changes.extend(
                    {
                        **c,
                        "word": r.get("word_gb"),
                        "pos": r.get("lexical_category"),
                        "field": key,
                    }
                    for c in changes
                )
            if fixed != original:
                r[key] = fixed
                entry_changed = True
            if not fixed:
                empty_after.append(
                    {
                        "word": r.get("word_gb"),
                        "pos": r.get("lexical_category"),
                        "field": key,
                        "original": original,
                    }
                )
        if entry_changed:
            n_repaired_entries += 1

    report = {
        "checked_primary": len(all_urls),
        "primary_dead": len(dead_primary),
        "repaired_entries": n_repaired_entries,
        "changes": all_changes,
        "still_empty": empty_after,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"repaired entries={n_repaired_entries} changes={len(all_changes)} "
        f"still_empty={len(empty_after)}",
        flush=True,
    )
    for c in all_changes:
        print(f"  {c['status']}: {c['word']} {c['field']}", flush=True)
        print(f"    from: {c['from']}", flush=True)
        print(f"    to:   {c['to']}", flush=True)

    if empty_after:
        print("WARNING: some entries lost all audio for a field:", flush=True)
        for e in empty_after:
            print(f"  {e}", flush=True)

    if not args.check_only:
        write_outputs(records)
        print(f"Updated {JSON_PATH} and {CSV_PATH}", flush=True)
        # patch meta note
        meta_path = OUT_DIR / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["audio_verify"] = {
                "checked_primary": len(all_urls),
                "primary_dead": len(dead_primary),
                "repaired_entries": n_repaired_entries,
                "changes": len(all_changes),
                "still_empty": len(empty_after),
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )


if __name__ == "__main__":
    main()
