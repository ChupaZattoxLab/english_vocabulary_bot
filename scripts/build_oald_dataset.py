"""
Build a separate OALD-parsed dataset (no translations).

Reads Oxford 3000∪5000 URLs from nalgeon oxford-5k.csv, downloads definition
pages into source/oald_html/, parses them with parse_oald_entry.py, writes:

  data/oald/words.csv
  data/oald/words.json
  data/oald/meta.json

Schema (translations omitted):
  word_us, word_gb, lexical_category, cefr, ipa_us, ipa_gb,
  definition, example, audio_source_us, audio_source_gb

Usage:
  python scripts/build_oald_dataset.py --limit 5          # smoke test
  python scripts/build_oald_dataset.py                   # full run (resume-safe)
  python scripts/build_oald_dataset.py --parse-only      # re-parse cached HTML
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from parse_oald_entry import (  # noqa: E402
    abs_url,
    first_phrasal_ref,
    is_american_spelling_of,
    load_html,
    looks_like_spelling_variant,
    parse_entry,
    text_of,
)
from parse_cambridge_entry import (  # noqa: E402
    load_html as load_cambridge_html,
    parse_entry as parse_cambridge,
)
from audit_esdb_spellings import (  # noqa: E402
    ESDB,
    ensure_files as ensure_esdb_files,
    load_wordlist as load_esdb_wordlist,
    parse_scowl_pairs,
    preferred as esdb_preferred,
)

WORDLIST = ROOT / "source" / "nalgeon-words" / "data" / "oxford-5k.csv"
HTML_DIR = ROOT / "source" / "oald_html"
CAMBRIDGE_DIR = ROOT / "source" / "cambridge_html"
OUT_DIR = ROOT / "data" / "oald"

SCHEMA_COLS = [
    "word_us",
    "word_gb",
    "lexical_category",
    "cefr",  # a1–c1 from OALD ox3k/ox5k / sense@cefr
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

# Broken / empty definition_url values in oxford-5k.csv
URL_OVERRIDES: dict[tuple[str, str], str] = {
    ("retail", "noun"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/retail_1"
    ),
    ("yield", "verb"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/yield_2"
    ),
    # OALD renumbered: adjective is empty_1, verb empty_2 (noun empty_3)
    ("empty", "adjective"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/empty_1"
    ),
    ("empty", "verb"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/empty_2"
    ),
    # pace_1 redirects to PACE (Police Act); real verb is pace1_2
    ("pace", "verb"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/pace1_2"
    ),
    # Wordlist POS index often off-by-one vs current OALD numbering
    ("collect", "verb"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/collect_1"
    ),
    ("constitutional", "adjective"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/constitutional_1"
    ),
    ("dry", "verb"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/dry_3"
    ),
    ("favourite", "adjective"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/favourite_1"
    ),
    ("favourite", "noun"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/favourite_2"
    ),
    ("sing", "verb"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/sing_1"
    ),
    # long-term_1/2 were swapped in the wordlist
    ("long-term", "adjective"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/long-term_1"
    ),
    ("long-term", "adverb"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/long-term_2"
    ),
    # oxford-5k.csv wrongly points mission → impossible
    ("mission", "noun"): (
        "https://www.oxfordlearnersdictionaries.com/definition/english/mission"
    ),
}

# Manual CEFR when OALD page has no ox3k/ox5k / sense@cefr
CEFR_OVERRIDES: dict[tuple[str, str], str] = {
    ("accounting", "noun"): "b2",
    ("angrily", "adverb"): "b1",
    ("cleaning", "noun"): "b1",
    ("feeding", "noun"): "b1",
}

CAMBRIDGE_ENTRY = "https://dictionary.cambridge.org/dictionary/english/{slug}"

# Extra US spellings when OALD omits type=vs but ESDB/breame agree
SPELLING_US_OVERRIDES: dict[str, str] = {
    # kept as safety net; parser + ESDB usually cover these
}


def load_spelling_helpers() -> tuple[dict, set[str], set[str]]:
    """ESDB A↔B pairs + US/GB wordlists for spelling normalization."""
    ensure_esdb_files()
    pairs = parse_scowl_pairs(ESDB / "scowl.txt")
    us_list = load_esdb_wordlist(ESDB / "en_US.txt")
    gb_list = load_esdb_wordlist(ESDB / "en_GB-ize.txt") | load_esdb_wordlist(
        ESDB / "en_GB-ise.txt"
    )
    return pairs, us_list, gb_list


def apply_us_gb_spelling(
    entry,
    pairs: dict,
    us_list: set[str],
    gb_list: set[str],
) -> None:
    """Keep word_us/word_gb as orthographic variants only; align with ESDB."""
    gb = (entry.word_gb or "").strip()
    us = (entry.word_us or "").strip()
    if not gb:
        return

    # Drop lexical synonyms / parser junk (forget→also, petrol→gas, …)
    if (
        us
        and us.lower() != gb.lower()
        and not is_american_spelling_of(gb, us)
        and not looks_like_spelling_variant(gb, us)
    ):
        entry.word_us = gb
        us = gb

    gb_l, us_l = gb.lower(), (entry.word_us or gb).lower()
    override = SPELLING_US_OVERRIDES.get(gb_l)
    if override:
        entry.word_us = override
        return

    info = pairs.get(gb_l) or pairs.get(us_l) or {}
    us_forms = set(info.get("us") or [])
    gb_forms = set(info.get("gb") or [])
    if us_forms and gb_forms:
        exp_us = esdb_preferred(us_forms, us_l if us_l in us_forms else None)
        if (
            exp_us
            and exp_us in us_forms
            and is_american_spelling_of(gb, exp_us)
        ):
            entry.word_us = exp_us
            return

    # Fix swapped -ize/-ise if parser previously stored British on word_us
    if us_l != gb_l and not is_american_spelling_of(gb, entry.word_us or ""):
        entry.word_us = gb
        us_l = gb_l

    # Already have a correct spelling split from OALD
    if us_l != gb_l and is_american_spelling_of(gb, entry.word_us or ""):
        return

    # breame for pairs SCOWL indexes poorly (grey/gray). Skip when the GB
    # form is already standard American too (tonne ∈ US∩GB).
    try:
        from breame.spelling import get_american_spelling
    except ImportError:
        return
    try:
        am = (get_american_spelling(gb_l) or "").lower()
    except Exception:  # noqa: BLE001
        return
    if not am or am == gb_l or not looks_like_spelling_variant(gb_l, am):
        return
    if am not in us_list or gb_l not in gb_list:
        return
    if gb_l in us_list:
        # Both spellings live in American English — need explicit ESDB split
        return
    entry.word_us = am


def slug_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or "unknown"


def html_path(url: str) -> Path:
    return HTML_DIR / f"{slug_from_url(url)}.html"


def cambridge_slug(word: str) -> str:
    """Map headword to Cambridge URL slug."""
    w = word.strip().lower()
    w = re.sub(r"\s+\d+$", "", w)
    w = w.replace(" ", "-")
    w = re.sub(r"[^a-z0-9\-']", "", w)
    return w


def cambridge_path(word: str) -> Path:
    return CAMBRIDGE_DIR / f"{cambridge_slug(word)}.html"


def phrasal_links(entry_soup_root) -> list[tuple[str, str]]:
    """All Phrasal Verb cross-refs on an OALD stub page."""
    aside = entry_soup_root.select_one("aside.phrasal_verb_links")
    if aside is None:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for link in aside.select("a.Ref[href], a[href]"):
        label = text_of(link.select_one(".xh") or link)
        href = abs_url(link.get("href"))
        if not label or not href:
            continue
        # strip fragment for caching
        base = href.split("#", 1)[0]
        if base in seen:
            continue
        seen.add(base)
        out.append((label, base))
    return out


def rank_phrasal(label: str) -> int:
    """Prefer common particle phrases (of/on/to) over rarer ones."""
    l = label.lower()
    if re.search(r"\bof\b", l):
        return 0
    if re.search(r"\bon\b", l):
        return 1
    if re.search(r"\bto\b", l):
        return 2
    if re.search(r"\bfrom\b", l):
        return 3
    return 5


def fill_definition_from_phrasal(
    entry,
    root,
    *,
    parse_only: bool,
    sleep: float,
    force: bool,
) -> bool:
    """If entry has no definition, try linked OALD phrasal-verb pages."""
    if (entry.definition or "").strip():
        return False
    links = phrasal_links(root)
    if not links and first_phrasal_ref(root):
        label, href = first_phrasal_ref(root)
        links = [(label, href.split("#", 1)[0])]
    if not links:
        return False
    links.sort(key=lambda t: rank_phrasal(t[0]))
    for _label, href in links:
        dest = html_path(href)
        if not parse_only:
            need = force or not dest.exists() or dest.stat().st_size < 500
            if need:
                ok, msg = fetch_html(href, dest)
                if not ok:
                    continue
                time.sleep(sleep)
        if not dest.exists():
            continue
        try:
            pv = parse_entry(load_html(dest), source_url=href)
        except Exception:  # noqa: BLE001
            continue
        if (pv.definition or "").strip():
            entry.definition = pv.definition
            if not (entry.example or "").strip() and pv.example:
                entry.example = pv.example
            # keep stub headword/POS/IPA; only borrow sense text
            return True
    return False


def fill_definition_from_cambridge(
    entry,
    wordlist_word: str,
    wordlist_pos: str,
    *,
    parse_only: bool,
    sleep: float,
    force: bool,
) -> bool:
    """Cambridge Dictionary fallback when OALD still has no definition."""
    if (entry.definition or "").strip():
        return False
    word = (entry.word_gb or wordlist_word or "").strip()
    if not word:
        return False
    dest = cambridge_path(word)
    url = CAMBRIDGE_ENTRY.format(slug=cambridge_slug(word))
    if not parse_only:
        need = force or not dest.exists() or dest.stat().st_size < 500
        if need:
            ok, msg = fetch_cambridge(url, dest)
            if not ok:
                return False
            time.sleep(sleep)
    if not dest.exists():
        return False
    try:
        sense = parse_cambridge(load_cambridge_html(dest), prefer_pos=wordlist_pos)
    except Exception:  # noqa: BLE001
        return False
    if not (sense.definition or "").strip():
        return False
    entry.definition = sense.definition
    if not (entry.example or "").strip() and sense.example:
        entry.example = sense.example
    if not (entry.cefr or "").strip() and sense.cefr:
        entry.cefr = sense.cefr
    return True


def fetch_cambridge(url: str, dest: Path, timeout: float = 30.0) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    if "ddef_d" not in text and "ddef_block" not in text and "def ddef" not in text:
        return False, "no cambridge def markup"
    dest.write_text(text, encoding="utf-8")
    return True, f"saved {len(text)} bytes"


def fetch_html(url: str, dest: Path, timeout: float = 30.0) -> tuple[bool, str]:
    """Download page to dest. Returns (ok, message)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"URL error: {e.reason}"
    except TimeoutError:
        return False, "timeout"

    text = body.decode("utf-8", errors="ignore")
    if "entryContent" not in text and 'class="entry"' not in text:
        # soft block / captcha / empty shell
        hint = "no entry markup"
        if "captcha" in text.lower() or "cf-browser-verification" in text.lower():
            hint = "blocked/captcha"
        return False, hint

    dest.write_text(text, encoding="utf-8")
    _ = ctype
    return True, f"saved {len(text)} bytes"


def load_wordlist(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            word = (row.get("word") or "").strip()
            pos = (row.get("pos") or "").strip()
            url = (row.get("definition_url") or "").strip()
            override = URL_OVERRIDES.get((word.lower(), pos.lower()))
            if override:
                url = override
            # Skip empty / index-only URLs
            if not url or url.rstrip("/").endswith("/english"):
                if not override:
                    continue
            rows.append(
                {
                    "word": word,
                    "level": (row.get("level") or "").strip(),
                    "pos": pos,
                    "definition_url": url,
                    "voice_url": (row.get("voice_url") or "").strip(),
                }
            )
    return rows


def entry_to_row(entry, source_url: str = "") -> dict:
    word_gb = entry.word_gb
    return {
        "word_us": entry.word_us,
        "word_gb": word_gb,
        "lexical_category": entry.lexical_category,
        "cefr": entry.cefr,
        "definition_url_oxford": (source_url or entry.source_url or "").split("#", 1)[0],
        "definition_url_cambridge": (
            CAMBRIDGE_ENTRY.format(slug=cambridge_slug(word_gb)) if word_gb else ""
        ),
        "ipa_us": entry.ipa_us,
        "ipa_gb": entry.ipa_gb,
        "definition": entry.definition,
        "example": entry.example,
        "audio_source_us": entry.audio_source_us,
        "audio_source_gb": entry.audio_source_gb,
        "_source_url": source_url or entry.source_url,
        "_entry_id": entry.entry_id,
    }


def write_outputs(records: list[dict], meta_extra: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # CSV: nested lists as JSON strings
    csv_path = OUT_DIR / "words.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
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

    json_path = OUT_DIR / "words.json"
    clean = [{k: r[k] for k in SCHEMA_COLS} for r in records]
    json_path.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    n = len(records)
    with_def = sum(1 for r in records if r.get("definition"))
    with_ex = sum(1 for r in records if r.get("example"))
    with_ipa_us = sum(1 for r in records if r.get("ipa_us"))
    with_ipa_gb = sum(1 for r in records if r.get("ipa_gb"))
    with_cefr = sum(1 for r in records if r.get("cefr"))
    us_gb_diff = sum(
        1 for r in records if (r.get("word_us") or "") != (r.get("word_gb") or "")
    )
    cefr_hist: dict[str, int] = {}
    for r in records:
        lvl = (r.get("cefr") or "").lower() or "(empty)"
        cefr_hist[lvl] = cefr_hist.get(lvl, 0) + 1

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "OALD definition pages via parse_oald_entry.py",
        "wordlist": str(WORDLIST.relative_to(ROOT)).replace("\\", "/"),
        "schema": SCHEMA_COLS,
        "note": "translations intentionally omitted; cefr from OALD sense/webtop",
        "counts": {
            "entries": n,
            "with_definition": with_def,
            "with_example": with_ex,
            "with_ipa_us": with_ipa_us,
            "with_ipa_gb": with_ipa_gb,
            "with_cefr": with_cefr,
            "distinct_us_gb_spelling": us_gb_diff,
            "cefr_histogram": dict(sorted(cefr_hist.items())),
        },
        **meta_extra,
    }
    (OUT_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {OUT_DIR / 'meta.json'}")
    print(
        f"entries={n} def={with_def} ex={with_ex} "
        f"ipa_us={with_ipa_us} ipa_gb={with_ipa_gb} cefr={with_cefr} us≠gb={us_gb_diff}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="Process only first N URLs")
    ap.add_argument("--sleep", type=float, default=0.4, help="Delay between downloads")
    ap.add_argument("--force", action="store_true", help="Re-download even if cached")
    ap.add_argument(
        "--parse-only",
        action="store_true",
        help="Do not download; only parse existing HTML cache",
    )
    ap.add_argument(
        "--max-downloads",
        type=int,
        default=0,
        help="Stop after this many network downloads (0=unlimited)",
    )
    args = ap.parse_args()

    if not WORDLIST.exists():
        sys.exit(f"Wordlist not found: {WORDLIST}")

    rows = load_wordlist(WORDLIST)
    # Unique by definition_url, keep first wordlist metadata
    seen: set[str] = set()
    unique: list[dict] = []
    for r in rows:
        u = r["definition_url"]
        if u in seen:
            continue
        seen.add(u)
        unique.append(r)

    if args.limit > 0:
        unique = unique[: args.limit]

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    spelling_pairs, us_list, gb_list = load_spelling_helpers()

    downloads = 0
    fetch_ok = 0
    fetch_fail = 0
    parse_ok = 0
    parse_fail = 0
    records: list[dict] = []
    failures: list[dict] = []

    total = len(unique)
    print(f"URLs to process: {total} (from {len(rows)} wordlist rows)")

    for i, item in enumerate(unique, 1):
        url = item["definition_url"]
        dest = html_path(url)
        label = f"[{i}/{total}] {item['word']} ({item['pos']})"

        if not args.parse_only:
            need = args.force or not dest.exists() or dest.stat().st_size < 500
            if need:
                if args.max_downloads and downloads >= args.max_downloads:
                    print(f"{label}: max-downloads reached, stopping fetch")
                    break
                ok, msg = fetch_html(url, dest)
                downloads += 1
                if ok:
                    fetch_ok += 1
                    print(f"{label}: download OK ({msg})")
                else:
                    fetch_fail += 1
                    print(f"{label}: download FAIL ({msg})")
                    failures.append({"url": url, "stage": "fetch", "error": msg, **item})
                    if msg.startswith("HTTP 429") or msg == "blocked/captcha":
                        print("Rate-limited / blocked — stopping. Re-run later to resume.")
                        break
                    time.sleep(args.sleep)
                    continue
                time.sleep(args.sleep)
            else:
                if i % 200 == 0 or i == 1:
                    print(f"{label}: cache hit")

        if not dest.exists():
            parse_fail += 1
            failures.append(
                {"url": url, "stage": "missing_html", "error": "no cache", **item}
            )
            continue

        try:
            soup = load_html(dest)
            entry = parse_entry(soup, source_url=url)
            root = soup.select_one("#entryContent .entry") or soup.select_one(".entry")
            wl_pos = (item["pos"] or "").strip()
            page_pos = (entry.lexical_category or "").strip()

            # Hard mismatch: page is a different POS than the wordlist asked for.
            # (Stale oxford-5k URLs.) Record and skip rather than keep wrong sense.
            if (
                wl_pos
                and page_pos
                and wl_pos.lower() != page_pos.lower()
                and not (
                    # allow combined labels like "adjective , adverb"
                    wl_pos.lower() in page_pos.lower()
                    or page_pos.lower() in wl_pos.lower()
                )
            ):
                parse_fail += 1
                failures.append(
                    {
                        "url": url,
                        "stage": "pos_mismatch",
                        "error": f"want {wl_pos}, page has {page_pos}",
                        "page_word": entry.word_gb,
                        **item,
                    }
                )
                print(f"{label}: POS mismatch want={wl_pos} page={page_pos} — skip")
                continue

            # Stale wordlist URL may point at another POS (e.g. empty_3 = noun).
            # Only force wordlist POS when the page has no usable non-idiom sense.
            if (
                root is not None
                and wl_pos
                and page_pos
                and wl_pos.lower() != page_pos.lower()
            ):
                defined = [
                    s
                    for s in root.select("li.sense")
                    if s.select_one("span.def, .def")
                ]
                only_idioms = defined and all(
                    s.find_parent("div", class_="idioms") for s in defined
                )
                if only_idioms or not (entry.definition or "").strip():
                    entry.definition = ""
                    entry.example = ""
                    entry.lexical_category = wl_pos
            elif wl_pos and not page_pos:
                entry.lexical_category = wl_pos

            # Prefer wordlist headword casing when page is ALL-CAPS acronym of same letters
            wl_word = (item["word"] or "").strip()
            if wl_word and entry.word_gb and entry.word_gb.upper() == wl_word.upper():
                if entry.word_gb != wl_word and (
                    entry.word_gb.isupper() or wl_word.isupper()
                ):
                    # keep OALD canonical casing for AIDS/CD/TV; only fix PACE-style wrong pages
                    pass
            # Strip accidental homograph digits (pace1)
            entry.word_gb = re.sub(r"(?<=\D)\d+$", "", entry.word_gb).strip()
            entry.word_us = re.sub(r"(?<=\D)\d+$", "", entry.word_us).strip()
            if wl_word and not entry.word_gb:
                entry.word_gb = wl_word
                entry.word_us = wl_word

            apply_us_gb_spelling(entry, spelling_pairs, us_list, gb_list)

            if not entry.cefr:
                override_lvl = CEFR_OVERRIDES.get(
                    (item["word"].lower(), item["pos"].lower())
                ) or CEFR_OVERRIDES.get(
                    (entry.word_gb.lower(), (entry.lexical_category or "").lower())
                )
                if override_lvl:
                    entry.cefr = override_lvl
                elif item["level"]:
                    entry.cefr = item["level"]

            filled = ""
            if root is not None and not (entry.definition or "").strip():
                if fill_definition_from_phrasal(
                    entry,
                    root,
                    parse_only=args.parse_only,
                    sleep=args.sleep,
                    force=args.force,
                ):
                    filled = "oald-phrasal"
            if not (entry.definition or "").strip():
                if fill_definition_from_cambridge(
                    entry,
                    item["word"],
                    item["pos"],
                    parse_only=args.parse_only,
                    sleep=args.sleep,
                    force=args.force,
                ):
                    filled = "cambridge"

            row = entry_to_row(entry, source_url=url)
            if filled:
                row["_def_source"] = filled
                print(f"{label}: def filled via {filled}")
            records.append(row)
            parse_ok += 1
        except Exception as e:  # noqa: BLE001 — keep going on bad pages
            parse_fail += 1
            failures.append(
                {"url": url, "stage": "parse", "error": str(e), **item}
            )
            print(f"{label}: parse FAIL ({e})")

    write_outputs(
        records,
        {
            "fetch": {
                "downloads": downloads,
                "ok": fetch_ok,
                "fail": fetch_fail,
            },
            "parse": {"ok": parse_ok, "fail": parse_fail},
            "html_cache": str(HTML_DIR.relative_to(ROOT)).replace("\\", "/"),
            "cambridge_cache": str(CAMBRIDGE_DIR.relative_to(ROOT)).replace("\\", "/"),
            "failures_count": len(failures),
            "def_fill_oald_phrasal": sum(
                1 for r in records if r.get("_def_source") == "oald-phrasal"
            ),
            "def_fill_cambridge": sum(
                1 for r in records if r.get("_def_source") == "cambridge"
            ),
        },
    )

    if failures:
        fail_path = OUT_DIR / "failures.json"
        fail_path.write_text(
            json.dumps(failures, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {fail_path} ({len(failures)} failures)")
    else:
        fail_path = OUT_DIR / "failures.json"
        if fail_path.exists():
            fail_path.unlink()
            print("No failures (removed stale failures.json)")


if __name__ == "__main__":
    main()
