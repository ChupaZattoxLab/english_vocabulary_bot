"""Fill EN→RU translations from Mueller 7th edition (dictd UTF-8 dump).

Source:
  source/mueller/mueller7.dict
  https://github.com/krvkir/cldict-mueller

Writes into data/oald/words.{json,csv}:
  translations  — {"ru": ["…", …]}  (all Mueller glosses for the lemma/POS)

Usage:
  python scripts/enrich_mueller_translations.py
"""

from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUELLER_DIR = ROOT / "source" / "mueller"
DICT_PATH = MUELLER_DIR / "mueller7.dict"
INDEX_PATH = MUELLER_DIR / "mueller7.index"

OUT_DIR = ROOT / "data" / "oald"
JSON_PATH = OUT_DIR / "words.json"
CSV_PATH = OUT_DIR / "words.csv"
META_PATH = OUT_DIR / "meta.json"

DICT_URL = (
    "https://raw.githubusercontent.com/krvkir/cldict-mueller/master/"
    "dict/mueller7/mueller7.dict"
)
INDEX_URL = (
    "https://raw.githubusercontent.com/krvkir/cldict-mueller/master/"
    "dict/mueller7/mueller7.index"
)

SCHEMA = [
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
    "translations",
]

POS_TAGS: dict[str, set[str]] = {
    "_n.": {"noun"},
    "_n-card.": {"number"},
    "_n-ord.": {"ordinal number"},
    "_v.": {"verb", "modal verb", "auxiliary verb", "linking verb"},
    "_a.": {"adjective"},
    "_adv.": {"adverb"},
    "_prep.": {"preposition"},
    "_cj.": {"conjunction"},
    "_conj.": {"conjunction"},
    "_pron.": {"pronoun", "determiner"},
    "_int.": {"exclamation"},
    "_num.": {"number", "ordinal number"},
    "_a": {"adjective"},
}

# Multiword / missing Mueller headwords — curated RU lists
PHRASE_OVERRIDES: dict[tuple[str, str], list[str]] = {
    ("have to", "modal verb"): ["должен", "приходится", "надо"],
    ("used to", "modal verb"): ["раньше", "бывало", "имел обыкновение"],
    ("ought to", "modal verb"): ["следует", "должен"],
    ("according to", "preposition"): ["согласно", "по словам", "по мнению"],
    ("any more", "adverb"): ["больше не"],
    ("next to", "preposition"): ["рядом с", "около"],
    ("all right", "adjective , adverb"): ["хорошо", "в порядке", "ладно"],
    ("all right", "exclamation"): ["ладно", "хорошо"],
    ("film-maker", "noun"): ["кинорежиссёр", "кинематографист", "режиссёр"],
    ("no one", "pronoun"): ["никто"],
    ("per cent", "noun"): ["процент"],
    ("per cent", "adjective , adverb"): ["процентный", "на процент"],
    ("o'clock", "adverb"): ["часов"],
    ("o’clock", "adverb"): ["часов"],
    ("the accused", "noun"): ["обвиняемый", "подсудимый"],
    ("the mainland", "noun"): ["материк", "континент"],
    ("thought-provoking", "adjective"): ["наводящий на размышления", "заставляющий задуматься"],
    ("long-standing", "adjective"): ["давний", "продолжительный"],
    ("long-time", "adjective"): ["давний", "многолетний"],
    ("post-war", "adjective"): ["послевоенный"],
    ("T-shirt", "noun"): ["футболка"],
    ("ice cream", "noun"): ["мороженое"],
}

HEADWORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9'\-]*(?:\s+[A-Za-z][A-Za-z0-9'\-]*)*$")
POS_LINE_RE = re.compile(r"(_(?:n-card|n-ord|n|v|a|adv|prep|cj|conj|pron|int|num)\.)")
GLOSS_RE = re.compile(r"^\s+\d+\)\s*(.+)$")
LABEL_RE = re.compile(r"_[а-яёa-z]+\.?", re.I)


def ensure_mueller() -> None:
    MUELLER_DIR.mkdir(parents=True, exist_ok=True)
    if DICT_PATH.exists() and DICT_PATH.stat().st_size > 1_000_000:
        return
    print("Downloading Mueller dict…", flush=True)
    for url, dest in ((DICT_URL, DICT_PATH), (INDEX_URL, INDEX_PATH)):
        req = urllib.request.Request(url, headers={"User-Agent": "vocab-bot/0.1"})
        dest.write_bytes(urllib.request.urlopen(req, timeout=180).read())
        print(f"  {dest.name} {dest.stat().st_size}", flush=True)


def clean_gloss(text: str) -> str:
    text = LABEL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ;,")
    return text


def split_ru_equivalents(chunk: str) -> list[str]:
    """Split a Mueller gloss line into short RU equivalents."""
    out: list[str] = []
    chunk = re.split(r";\s*(?=[A-Za-z])", chunk, maxsplit=1)[0]
    chunk = clean_gloss(chunk)
    if not chunk:
        return out

    for part in re.split(r"[;]", chunk):
        part = part.strip(" ,;")
        if not part:
            continue
        cyr = len(re.findall(r"[А-Яа-яЁё]", part))
        lat = len(re.findall(r"[A-Za-z]", part))
        if cyr < 2 or lat > cyr:
            continue
        if "," in part and len(part) < 120:
            for sub in part.split(","):
                sub = sub.strip()
                sc = len(re.findall(r"[А-Яа-яЁё]", sub))
                if sc >= 2 and not re.search(r"[A-Za-z]{4,}", sub):
                    if sub.count("(") > sub.count(")"):
                        sub += ")"
                    out.append(sub)
        else:
            part = re.sub(r"\s+\([^)]*$", "", part).strip()
            if part.count("(") > part.count(")"):
                part += ")"
            if not re.search(r"[A-Za-z]{4,}", part):
                out.append(part)
            else:
                m = re.match(r"^([^A-Za-z]+)", part)
                if m:
                    p = m.group(1).strip(" ,;")
                    if len(re.findall(r"[А-Яа-яЁё]", p)) >= 2:
                        out.append(p)

    uniq: list[str] = []
    for g in out:
        g = g.strip(" ,;")
        if g and g not in uniq:
            uniq.append(g)
    return uniq


def extract_glosses(block: str) -> list[str]:
    glosses: list[str] = []
    for line in block.splitlines():
        m = GLOSS_RE.match(line)
        if m:
            glosses.extend(split_ru_equivalents(m.group(1)))

    if not glosses:
        for line in block.splitlines():
            m = re.search(
                r"_(?:n-card|n-ord|n|v|a|adv|prep|cj|conj|pron|int|num)\."
                r"\s*(?:_[a-zа-яё.]+\s*)*(.+)$",
                line,
                re.I,
            )
            if m:
                glosses.extend(split_ru_equivalents(m.group(1)))

    # keep all unique
    uniq: list[str] = []
    for g in glosses:
        if g and g not in uniq:
            uniq.append(g)
    return uniq


def parse_entry(_head: str, body: str) -> dict[str, list[str]]:
    by_pos: dict[str, list[str]] = defaultdict(list)
    parts = re.split(r"(?=^\s*\d+\.\s*_|^   _)", body, flags=re.M)
    if len(parts) <= 1:
        glosses = extract_glosses(body)
        if not glosses:
            for line in body.splitlines():
                if re.search(r"[А-Яа-яЁё]{3,}", line) and not line.strip().startswith(
                    "["
                ):
                    g = clean_gloss(re.sub(r"^\s*\d+\)\s*", "", line))
                    g = re.sub(r"^\[.*?\]\s*", "", g)
                    if g and not re.match(r"^[A-Za-z]", g):
                        glosses.extend(split_ru_equivalents(g))
        if glosses:
            by_pos["_"] = glosses
        return dict(by_pos)

    for part in parts:
        tags = POS_LINE_RE.findall(part)
        tag = tags[0] if tags else "_"
        glosses = extract_glosses(part)
        if glosses:
            by_pos[tag].extend(g for g in glosses if g not in by_pos[tag])
    return dict(by_pos)


def parse_mueller(path: Path) -> dict[str, dict[str, list[str]]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    entries: dict[str, dict[str, list[str]]] = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line or line.startswith("00-") or line.startswith("http"):
            i += 1
            continue
        if line.startswith(" ") or line.startswith("\t"):
            i += 1
            continue
        head = line.strip()
        if not HEADWORD_RE.match(head):
            i += 1
            continue
        i += 1
        body_lines: list[str] = []
        while i < n:
            nxt = lines[i]
            if (
                nxt
                and not nxt.startswith(" ")
                and not nxt.startswith("\t")
                and HEADWORD_RE.match(nxt.strip())
            ):
                break
            body_lines.append(nxt)
            i += 1
        parsed = parse_entry(head, "\n".join(body_lines))
        if not parsed:
            continue
        key = head.lower()
        if key not in entries:
            entries[key] = parsed
        else:
            for tag, glosses in parsed.items():
                entries[key].setdefault(tag, [])
                for g in glosses:
                    if g not in entries[key][tag]:
                        entries[key][tag].append(g)
    return entries


def dataset_pos_atoms(pos: str) -> list[str]:
    return [p.strip().lower() for p in re.split(r"\s*,\s*", pos or "") if p.strip()]


def lookup_keys(row: dict) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for w in (row.get("word_gb"), row.get("word_us")):
        if not w:
            continue
        cands = [
            w.strip().lower(),
            re.sub(r"^the\s+", "", w.strip().lower()),
            w.strip().lower().replace("-", " "),
            w.strip().lower().replace(" ", "-"),
            w.strip().lower().replace("'", "'").replace("\u2019", "'"),
        ]
        for c in cands:
            if c and c not in seen:
                seen.add(c)
                keys.append(c)
    return keys


def pick_all_for_pos(entry: dict[str, list[str]], dataset_pos: str) -> list[str]:
    """All unique RU glosses matching dataset POS (or full entry fallback)."""
    atoms = dataset_pos_atoms(dataset_pos)
    matched: list[str] = []
    for tag, ours in POS_TAGS.items():
        if tag not in entry:
            continue
        if any(a in ours for a in atoms):
            for g in entry[tag]:
                if g not in matched:
                    matched.append(g)
    if matched:
        return matched
    # no POS match — take everything Mueller has for the lemma
    for glosses in entry.values():
        for g in glosses:
            if g not in matched:
                matched.append(g)
    return matched


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
                row[lk] = json.dumps(row[lk], ensure_ascii=False)
            w.writerow(row)
    clean = [{k: r.get(k) for k in SCHEMA} for r in rows]
    JSON_PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    ensure_mueller()
    print("Parsing Mueller…", flush=True)
    lexicon = parse_mueller(DICT_PATH)
    print(f"Mueller headwords: {len(lexicon)}", flush=True)

    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    stats = Counter()
    gloss_counts: list[int] = []

    for r in rows:
        word = (r.get("word_gb") or "").strip()
        pos = r.get("lexical_category") or ""
        glosses: list[str] = []

        override = PHRASE_OVERRIDES.get((word.lower(), pos.lower().strip()))
        if override is None:
            # try without fancy apostrophe / the
            for k, v in PHRASE_OVERRIDES.items():
                if k[0] == word.lower().replace("\u2019", "'") and k[1] in pos.lower():
                    override = v
                    break
        if override:
            glosses = list(override)
            stats["override"] += 1
        else:
            entry = None
            for key in lookup_keys(r):
                if key in lexicon:
                    entry = lexicon[key]
                    break
            if entry:
                glosses = pick_all_for_pos(entry, pos)
                if glosses:
                    stats["mueller"] += 1
                else:
                    stats["mueller_empty"] += 1
            else:
                stats["missing"] += 1

        r["translations"] = {"ru": glosses} if glosses else {"ru": []}
        gloss_counts.append(len(glosses))
        if glosses:
            stats["with_ru"] += 1
        else:
            stats["without_ru"] += 1

    write_outputs(rows)

    with_ru = stats["with_ru"]
    meta = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    meta["schema"] = SCHEMA
    meta["translations"] = {
        "source": "mueller7 (krvkir/cldict-mueller)",
        "mueller_headwords": len(lexicon),
        "with_ru": with_ru,
        "without_ru": stats["without_ru"],
        "coverage_pct": round(100 * with_ru / max(len(rows), 1), 1),
        "stats": dict(stats),
        "avg_glosses": round(sum(gloss_counts) / max(len(rows), 1), 2),
        "max_glosses": max(gloss_counts) if gloss_counts else 0,
    }
    if "counts" in meta:
        meta["counts"]["with_translations_ru"] = with_ru
        meta["counts"]["entries"] = len(rows)
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"entries={len(rows)} with_ru={with_ru} ({meta['translations']['coverage_pct']}%)")
    print(f"stats={dict(stats)}")
    print(f"avg_glosses={meta['translations']['avg_glosses']} max={meta['translations']['max_glosses']}")
    print("samples:")
    shown = 0
    for r in rows:
        ru = (r.get("translations") or {}).get("ru") or []
        if ru and shown < 10:
            print(f"  {r['word_gb']:18} [{r['lexical_category']}] -> {ru[:6]}")
            shown += 1
    miss = [
        r["word_gb"]
        for r in rows
        if not ((r.get("translations") or {}).get("ru") or [])
    ]
    print(f"missing ({len(miss)}): {miss[:40]}")


if __name__ == "__main__":
    main()
