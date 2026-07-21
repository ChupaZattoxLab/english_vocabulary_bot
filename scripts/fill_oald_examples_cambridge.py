"""
Fill missing examples in data/oald from Cambridge Dictionary pages.

Usage:
  python scripts/fill_oald_examples_cambridge.py
  python scripts/fill_oald_examples_cambridge.py --sleep 0.4
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from parse_cambridge_entry import (  # noqa: E402
    is_weak_example,
    load_html,
    parse_entry,
)

OUT_DIR = ROOT / "data" / "oald"
JSON_PATH = OUT_DIR / "words.json"
CSV_PATH = OUT_DIR / "words.csv"
META_PATH = OUT_DIR / "meta.json"
CACHE_DIR = ROOT / "source" / "cambridge_html"

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

# Slug overrides when Cambridge URL differs from lowercased headword
SLUG_OVERRIDES: dict[str, str] = {
    "film-maker": "film-maker",
    "pace": "pace",  # OALD acronym PACE → ordinary pace page is wrong; curated below
}

# Learner-style examples when Cambridge has none / only number lists
CURATED: dict[tuple[str, str], str] = {
    ("eighteen", "number"): "She will be eighteen next month.",
    ("eighty", "number"): "My grandmother is eighty years old.",
    ("fifteen", "number"): "There are fifteen students in the class.",
    ("fifty", "number"): "He must be at least fifty.",
    ("forty", "number"): "She retired at forty.",
    ("fourteen", "number"): "He is fourteen years old.",
    ("nineteen", "number"): "She left home when she was nineteen.",
    ("ninety", "number"): "He lived to be ninety.",
    ("seventeen", "number"): "She is seventeen years old.",
    ("seventy", "number"): "My grandfather is seventy.",
    ("sixteen", "number"): "You can leave school at sixteen.",
    ("sixty", "number"): "She will turn sixty in May.",
    ("thirteen", "number"): "He is thirteen years old.",
    ("thirty", "number"): "She is about thirty.",
    ("thousand", "number"): "A thousand people came to the concert.",
    ("trillion", "number"): "The debt is more than a trillion dollars.",
    ("twenty", "number"): "There are twenty students in the class.",
    ("yeah", "exclamation"): "Yeah, I think you're right.",
    ("film-maker", "noun"): "Designers work as filmmakers, creating a script for their design movie.",
    ("martial", "adjective"): "Martial arts are popular worldwide.",
}


def cambridge_slug(word: str) -> str:
    w = word.strip().lower()
    w = re.sub(r"\s+\d+$", "", w)
    if w in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[w]
    w = w.replace(" ", "-")
    w = re.sub(r"[^a-z0-9\-']", "", w)
    return w


def cache_path(word: str) -> Path:
    return CACHE_DIR / f"{cambridge_slug(word)}.html"


def fetch(url: str, dest: Path, timeout: float = 30.0) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"URL error: {e.reason}"
    except TimeoutError:
        return False, "timeout"

    text = body.decode("utf-8", errors="ignore")
    if "ddef_d" not in text and "ddef_block" not in text:
        return False, "no cambridge markup"
    dest.write_text(text, encoding="utf-8")
    return True, f"saved {len(text)} bytes"


def write_outputs(records: list[dict]) -> None:
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
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--force", action="store_true", help="Re-download Cambridge HTML")
    args = ap.parse_args()

    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    missing = [
        (i, r)
        for i, r in enumerate(records)
        if not (r.get("example") or "").strip()
    ]
    print(f"missing examples: {len(missing)}", flush=True)

    filled = 0
    curated_n = 0
    failed: list[dict] = []

    for i, r in missing:
        word = r["word_gb"]
        pos = (r.get("lexical_category") or "").lower()
        key = (word.lower(), pos)
        label = f"{word} ({pos})"

        example = ""
        source = ""

        # Skip Cambridge for PACE acronym — page is ordinary "pace"
        if word.lower() == "pace" and pos == "verb":
            example = CURATED.get(key, "")
            source = "curated"
        else:
            dest = cache_path(word)
            url = f"https://dictionary.cambridge.org/dictionary/english/{cambridge_slug(word)}"
            need = args.force or not dest.exists() or dest.stat().st_size < 500
            if need:
                ok, msg = fetch(url, dest)
                print(f"{label}: fetch {ok} ({msg})", flush=True)
                if not ok:
                    failed.append({"word": word, "pos": pos, "error": msg})
                else:
                    time.sleep(args.sleep)
            if dest.exists():
                try:
                    sense = parse_entry(load_html(dest), prefer_pos=pos)
                    if sense.example and not is_weak_example(sense.example, word):
                        example = sense.example
                        source = "cambridge"
                except Exception as e:  # noqa: BLE001
                    failed.append({"word": word, "pos": pos, "error": str(e)})

        if not example and key in CURATED:
            example = CURATED[key]
            source = "curated"

        if example:
            records[i]["example"] = example
            filled += 1
            if source == "curated":
                curated_n += 1
            print(f"{label}: OK via {source} → {example[:80]}", flush=True)
        else:
            failed.append({"word": word, "pos": pos, "error": "no example"})
            print(f"{label}: FAIL", flush=True)

    write_outputs(records)

    still = sum(1 for r in records if not (r.get("example") or "").strip())
    with_ex = sum(1 for r in records if (r.get("example") or "").strip())

    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        meta.setdefault("counts", {})["with_example"] = with_ex
        meta["example_fill_cambridge"] = {
            "filled": filled,
            "curated": curated_n,
            "still_missing": still,
            "failed": failed,
        }
        META_PATH.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(
        f"done filled={filled} curated={curated_n} still_missing={still} "
        f"with_example={with_ex}/{len(records)}",
        flush=True,
    )
    if failed:
        print(f"failures: {len(failed)}", flush=True)
        for f in failed:
            print(f"  {f}", flush=True)


if __name__ == "__main__":
    main()
