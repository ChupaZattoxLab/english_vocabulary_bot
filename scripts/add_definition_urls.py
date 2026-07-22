"""Add Oxford + Cambridge definition URLs to data/oald words.

Columns:
  definition_url_oxford    — OALD page used for this entry (from wordlist + overrides)
  definition_url_cambridge — Cambridge Dictionary page for the same lemma

Usage:
  python scripts/add_definition_urls.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_oald_dataset import (  # noqa: E402
    WORDLIST,
    cambridge_slug as oald_cambridge_slug,
    html_path,
    load_wordlist,
)
from parse_oald_entry import load_html, parse_entry  # noqa: E402

OUT = ROOT / "data" / "oald"
JSON_PATH = OUT / "words.json"
CSV_PATH = OUT / "words.csv"
META_PATH = OUT / "meta.json"

OXFORD_COL = "definition_url_oxford"
CAMBRIDGE_COL = "definition_url_cambridge"
CAMBRIDGE_TMPL = "https://dictionary.cambridge.org/dictionary/english/{slug}"

SCHEMA = [
    "word_us",
    "word_gb",
    "lexical_category",
    "cefr",
    OXFORD_COL,
    CAMBRIDGE_COL,
    "ipa_us",
    "ipa_gb",
    "definition",
    "example",
    "audio_source_us",
    "audio_source_gb",
    "translations",
]

# Cambridge slug when it differs from naive lowercasing of word_gb
CAMBRIDGE_SLUG_OVERRIDES: dict[str, str] = {
    "film-maker": "film-maker",
    "o'clock": "o-clock",
    "o’clock": "o-clock",
    "per cent": "percent",
    "all right": "all-right",
    "any more": "anymore",
    "no one": "no-one",
    "used to": "used-to",
    "have to": "have-to",
    "ought to": "ought-to",
    "next to": "next-to",
    "according to": "according-to",
    "the accused": "accused",
    "the mainland": "mainland",
    "post-war": "postwar",
    "long-standing": "long-standing",
    "long-time": "long-time",
    "thought-provoking": "thought-provoking",
    "T-shirt": "t-shirt",
    "t-shirt": "t-shirt",
}


def norm_word(w: str) -> str:
    w = (w or "").strip().lower()
    w = re.sub(r"^the\s+", "", w)
    return w.replace("\u2019", "'").replace("\u2018", "'")


def norm_def(d: str) -> str:
    return re.sub(r"\s+", " ", (d or "").strip().lower())


def norm_pos(p: str) -> str:
    return (p or "").strip().lower()


def pos_compatible(a: str, b: str) -> bool:
    a, b = norm_pos(a), norm_pos(b)
    if not a or not b:
        return True
    if a == b:
        return True
    return a in b or b in a


def cambridge_url_for(word_gb: str) -> str:
    w = (word_gb or "").strip()
    key = w.lower().replace("\u2019", "'")
    if key in CAMBRIDGE_SLUG_OVERRIDES:
        slug = CAMBRIDGE_SLUG_OVERRIDES[key]
    else:
        slug = oald_cambridge_slug(w)
    return CAMBRIDGE_TMPL.format(slug=slug)


def clean_oxford_url(url: str) -> str:
    return (url or "").strip().split("#", 1)[0]


def unique_wordlist_urls() -> list[dict]:
    rows = load_wordlist(WORDLIST)
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        u = clean_oxford_url(r["definition_url"])
        if not u or u in seen:
            continue
        seen.add(u)
        out.append({**r, "definition_url": u})
    return out


def build_oxford_candidates() -> list[dict]:
    """One candidate per unique OALD URL, with parsed page def for matching."""
    cands: list[dict] = []
    for item in unique_wordlist_urls():
        url = item["definition_url"]
        dest = html_path(url)
        page_word = item["word"]
        page_pos = item["pos"]
        page_def = ""
        if dest.exists() and dest.stat().st_size > 500:
            try:
                entry = parse_entry(load_html(dest), source_url=url)
                page_word = entry.word_gb or page_word
                page_pos = entry.lexical_category or page_pos
                page_def = entry.definition or ""
            except Exception:  # noqa: BLE001
                pass
        cands.append(
            {
                "url": url,
                "wl_word": item["word"],
                "wl_pos": item["pos"],
                "page_word": page_word,
                "page_pos": page_pos,
                "page_def": page_def,
            }
        )
    return cands


def score_match(row: dict, cand: dict) -> float:
    rw = norm_word(row.get("word_gb") or "")
    ru = norm_word(row.get("word_us") or "")
    cw = norm_word(cand["page_word"])
    lw = norm_word(cand["wl_word"])
    cand_words = {cw, lw} - {""}

    if rw and rw in cand_words:
        word_score = 1.0
    elif ru and ru in cand_words and ru != rw:
        # US spelling alone is weaker — avoids disc(row)↔disk(url) swaps
        word_score = 0.55
    elif rw and any(
        rw == b or rw.startswith(b) or b.startswith(rw) for b in cand_words
    ):
        word_score = 0.7
    else:
        return -1.0

    if not pos_compatible(row.get("lexical_category") or "", cand["page_pos"]) and not pos_compatible(
        row.get("lexical_category") or "", cand["wl_pos"]
    ):
        return -1.0

    rd = norm_def(row.get("definition") or "")
    cd = norm_def(cand["page_def"])
    if rd and cd:
        def_score = SequenceMatcher(None, rd, cd).ratio()
    elif not cd:
        def_score = 0.5
    else:
        def_score = 0.0

    return word_score * 0.45 + def_score * 0.55


def assign_oxford(rows: list[dict], cands: list[dict]) -> tuple[int, int]:
    """Assign best unused Oxford URL to each row. Returns (matched, unmatched)."""
    # Index candidates by norm word for speed
    by_word: dict[str, list[int]] = {}
    for i, c in enumerate(cands):
        for w in {norm_word(c["page_word"]), norm_word(c["wl_word"])}:
            if not w:
                continue
            by_word.setdefault(w, []).append(i)
            # prefix variants
            if " " in w:
                by_word.setdefault(w.split()[-1], []).append(i)

    used: set[int] = set()
    unmatched = 0

    # First pass: unique high-confidence matches
    pending = list(range(len(rows)))
    assigned = 0

    for ri in pending:
        row = rows[ri]
        rw = norm_word(row.get("word_gb") or "")
        ru = norm_word(row.get("word_us") or "")
        idxs: list[int] = []
        # Prefer indexing by GB lemma first
        for w in [rw, ru]:
            if w:
                idxs.extend(by_word.get(w, []))
        # unique preserve order
        seen_i: set[int] = set()
        cand_idxs = []
        for i in idxs:
            if i not in seen_i and i not in used:
                seen_i.add(i)
                cand_idxs.append(i)

        if not cand_idxs:
            # broader scan (rare)
            scored = []
            for i, c in enumerate(cands):
                if i in used:
                    continue
                s = score_match(row, c)
                if s >= 0.7:
                    scored.append((s, i))
            scored.sort(reverse=True)
            if scored:
                best_s, best_i = scored[0]
                rows[ri][OXFORD_COL] = cands[best_i]["url"]
                used.add(best_i)
                assigned += 1
            else:
                rows[ri][OXFORD_COL] = ""
                unmatched += 1
            continue

        scored = [(score_match(row, cands[i]), i) for i in cand_idxs]
        scored = [(s, i) for s, i in scored if s >= 0]
        scored.sort(reverse=True)
        if not scored:
            rows[ri][OXFORD_COL] = ""
            unmatched += 1
            continue
        # Prefer exact GB lemma == wordlist/page headword
        exact = [
            (s, i)
            for s, i in scored
            if norm_word(cands[i]["wl_word"]) == rw
            or norm_word(cands[i]["page_word"]) == rw
        ]
        pool = exact if exact else scored
        best_s, best_i = max(pool, key=lambda t: t[0])
        rows[ri][OXFORD_COL] = cands[best_i]["url"]
        used.add(best_i)
        assigned += 1

    return assigned, unmatched


def write_outputs(rows: list[dict]) -> None:
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {k: r.get(k) for k in SCHEMA}
            for lk in (
                "ipa_us",
                "ipa_gb",
                "audio_source_us",
                "audio_source_gb",
                "translations",
            ):
                row[lk] = json.dumps(row.get(lk), ensure_ascii=False)
            w.writerow(row)
    clean = [{k: r.get(k) for k in SCHEMA} for r in rows]
    JSON_PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    print(f"entries={len(rows)}")
    print("Building Oxford candidates from wordlist + HTML cache…")
    cands = build_oxford_candidates()
    print(f"oxford candidates={len(cands)}")

    assigned, unmatched = assign_oxford(rows, cands)
    print(f"oxford assigned={assigned} unmatched={unmatched}")

    for r in rows:
        r[CAMBRIDGE_COL] = cambridge_url_for(r.get("word_gb") or "")

    # Sanity samples for homographs
    for w in ("lie", "march"):
        hits = [r for r in rows if norm_word(r["word_gb"]) == w]
        print(f"--- {w} ---")
        for r in hits:
            print(
                f"  {r['lexical_category']} cefr={r['cefr']} "
                f"ox={Path(r.get(OXFORD_COL) or '').name} "
                f"def={(r.get('definition') or '')[:50]!r}"
            )

    missing_ox = sum(1 for r in rows if not r.get(OXFORD_COL))
    missing_cam = sum(1 for r in rows if not r.get(CAMBRIDGE_COL))
    print(f"missing oxford={missing_ox} missing cambridge={missing_cam}")

    write_outputs(rows)

    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        meta["schema"] = SCHEMA
        meta["definition_urls"] = {
            "oxford_assigned": assigned,
            "oxford_unmatched": unmatched,
            "cambridge_all": len(rows) - missing_cam,
            "columns": [OXFORD_COL, CAMBRIDGE_COL],
        }
        if "counts" in meta:
            meta["counts"]["entries"] = len(rows)
            meta["counts"]["with_definition_url_oxford"] = len(rows) - missing_ox
            meta["counts"]["with_definition_url_cambridge"] = len(rows) - missing_cam
        META_PATH.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {CSV_PATH}")


if __name__ == "__main__":
    main()
