"""Audit word_us / word_gb against ESDB/SCOWL + breame.

Uses source/esdb/ from en-wl/wordlist-diff.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

try:
    from breame.spelling import get_american_spelling
except ImportError:
    get_american_spelling = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
ESDB = ROOT / "source" / "esdb"

# Defaults; overridden in main() via --dataset
WORDS_CSV = ROOT / "data" / "enriched" / "words.csv"
OUT_JSON = ROOT / "data" / "enriched" / "spelling_audit.json"
OUT_REPORT = ROOT / "data" / "enriched" / "spelling_audit.txt"

BASE = "https://raw.githubusercontent.com/en-wl/wordlist-diff/master/"
FILES = ["scowl.txt", "en_US.txt", "en_GB-ise.txt", "en_GB-ize.txt"]

VARIANT_RE = re.compile(
    r"^(?:\+|(?:[ABZCD_][.\=?v~V\-@x]*)(?:\s+[ABZCD_][.\=?v~V\-@x]*)*(?:\s+\{\d+\})?)$"
)
LEMMA_RE = re.compile(r"^(-|@|!)?([A-Za-z][A-Za-z0-9'\-]*)")

# Manual: same orthography in Oxford (-ize) GB and US is OK
OXFORD_IZE_OK = re.compile(r"iz(e|ed|es|ing|ation|ational|er|ers)$", re.I)


def ensure_files() -> None:
    ESDB.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        dest = ESDB / name
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        print("Downloading", name)
        req = urllib.request.Request(BASE + name, headers={"User-Agent": "vocab-bot/0.1"})
        dest.write_bytes(urllib.request.urlopen(req, timeout=120).read())


def load_wordlist(path: Path) -> set[str]:
    return {
        ln.strip().lower()
        for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if ln.strip() and not ln.startswith("#")
    }


def spelling_codes(variant: str) -> set[str]:
    if not variant or variant == "+":
        return set()
    return {tok[0] for tok in variant.split() if tok and tok[0] in "ABZCD_" and not tok.startswith("{")}


def parse_scowl_line(line: str) -> tuple[set[str], str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(": ")
    if len(parts) < 2:
        return None
    if VARIANT_RE.match(parts[1]):
        if len(parts) < 3:
            return None
        codes = spelling_codes(parts[1])
        lemma_info = parts[2]
    else:
        codes = set()
        lemma_info = parts[1]
    m = LEMMA_RE.match(lemma_info.strip())
    if not m:
        return None
    return codes, m.group(2).lower()


def looks_like_spelling_variant(a: str, b: str) -> bool:
    if a == b:
        return False
    # avoid pay/paycheck, idea/idaea-ish noise
    ratio = SequenceMatcher(None, a, b).ratio()
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    if len_ratio < 0.75 or abs(len(a) - len(b)) > 3:
        return False
    if ratio < 0.72:
        return False
    # idaea/idea is high ratio but not a dialect spelling — require shared prefix
    pref = 0
    for x, y in zip(a, b):
        if x != y:
            break
        pref += 1
    if pref < min(3, min(len(a), len(b)) // 2):
        return False
    return True


def parse_scowl_pairs(path: Path) -> dict[str, dict[str, set[str]]]:
    """form -> {us, gb} for clear A-only ↔ B-only spelling pairs in a group.

    Note: Z (Oxford -ize) is NOT merged into B. A∩Z words like 'organize'
    are American/Oxford and correctly may match word_gb on an Oxford list.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    groups = re.split(r"\n\s*\n", text)
    form_to_pair: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"us": set(), "gb": set()}
    )
    split_groups = 0

    for group in groups:
        by_code: dict[str, set[str]] = defaultdict(set)
        for line in group.splitlines():
            parsed = parse_scowl_line(line)
            if not parsed:
                continue
            codes, lemma = parsed
            if not codes:
                by_code["_"].add(lemma)
            else:
                for c in codes:
                    by_code[c].add(lemma)

        a = by_code.get("A", set())
        b = by_code.get("B", set())  # traditional -ise etc. — do NOT include Z
        a_only = a - b
        b_only = b - a
        # Keep only plausible orthographic pairs
        us_keep = set()
        gb_keep = set()
        for u in a_only:
            for g in b_only:
                if looks_like_spelling_variant(u, g):
                    us_keep.add(u)
                    gb_keep.add(g)
        if not us_keep or not gb_keep:
            continue
        split_groups += 1
        for f in us_keep | gb_keep:
            form_to_pair[f]["us"].update(us_keep)
            form_to_pair[f]["gb"].update(gb_keep)

    print(f"  clear A↔B spelling-variant groups: {split_groups}")
    return form_to_pair


def preferred(forms: set[str], hint: str | None = None) -> str | None:
    if not forms:
        return None
    if hint and hint in forms:
        return hint
    return sorted(forms, key=lambda x: (len(x), x))[0]


def dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        k = (it.get("word_gb"), it.get("word_us"), it.get("pos"), it.get("reason"), it.get("expected_us"))
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def main() -> None:
    import argparse

    global WORDS_CSV, OUT_JSON, OUT_REPORT

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dataset",
        choices=("enriched", "oald"),
        default="enriched",
        help="Which words.csv to audit (default: enriched)",
    )
    args = ap.parse_args()
    data_dir = ROOT / "data" / args.dataset
    WORDS_CSV = data_dir / "words.csv"
    OUT_JSON = data_dir / "spelling_audit.json"
    OUT_REPORT = data_dir / "spelling_audit.txt"

    ensure_files()
    print(f"Dataset: {args.dataset} ({WORDS_CSV})")
    print("Loading wordlists…")
    us_list = load_wordlist(ESDB / "en_US.txt")
    gb_ise = load_wordlist(ESDB / "en_GB-ise.txt")
    gb_ize = load_wordlist(ESDB / "en_GB-ize.txt")

    print("Parsing scowl.txt…")
    pairs = parse_scowl_pairs(ESDB / "scowl.txt")
    print(f"  indexed forms: {len(pairs)}")
    for w in ("colour", "color", "centre", "organize", "organise", "grey", "gray", "analyse"):
        print(f"  pair[{w}] = {dict(pairs.get(w, {}))}")

    rows = list(csv.DictReader(WORDS_CSV.open(encoding="utf-8")))

    ok_diff: list[dict] = []
    bad: list[dict] = []
    extra: list[dict] = []
    ok_same = 0

    for r in rows:
        w_us = (r.get("word_us") or "").strip()
        w_gb = (r.get("word_gb") or "").strip()
        us_l, gb_l = w_us.lower(), w_gb.lower()
        pos = r.get("lexical_category") or ""
        differ = us_l != gb_l

        info = pairs.get(gb_l) or pairs.get(us_l) or {}
        exp_us = preferred(set(info.get("us", [])), us_l if differ else None)
        exp_gb = preferred(set(info.get("gb", [])), gb_l)

        breame_us = None
        if get_american_spelling is not None:
            try:
                breame_us = get_american_spelling(gb_l).lower()
            except Exception:
                breame_us = None

        esdb_diff = bool(
            info.get("us")
            and info.get("gb")
            and exp_us
            and exp_gb
            and exp_us != exp_gb
        )

        # breame + dialect lists (skip -ize Oxford cases where GB lemma already American orthography)
        breame_diff = bool(
            breame_us
            and breame_us != gb_l
            and breame_us in us_list
            and (gb_l in gb_ise or gb_l in gb_ize)
        )
        # If GB lemma is Oxford -ize and equals US, not an error
        if breame_diff and gb_l in gb_ize and gb_l in us_list and breame_us == gb_l:
            breame_diff = False
        # tonne≠ton (different unit); GB form is valid in American English too
        if breame_diff and gb_l == "tonne":
            breame_diff = False
        # Keep identical columns when both are accepted American+Oxford forms
        if breame_diff and not differ and gb_l in us_list and breame_us in us_list:
            # only flag if ESDB has a clear A↔B split we missed
            if not esdb_diff:
                breame_diff = False

        entry = {
            "word_gb": w_gb,
            "word_us": w_us,
            "pos": pos,
            "expected_us": exp_us or breame_us,
            "expected_gb": exp_gb or gb_l,
        }

        if esdb_diff:
            us_ok = us_l in info["us"] or us_l == exp_us
            gb_ok = gb_l in info["gb"] or gb_l == exp_gb
            # Special case: our list uses Oxford -ize as word_gb (organize) while
            # ESDB B-form is organise — acceptable if word_us is American and
            # word_gb is valid GB-ize.
            oxford_ize_ok = (
                not differ
                and us_l in info["us"]
                and gb_l in gb_ize
                and gb_l in us_list
            )
            if differ and us_ok and gb_ok:
                ok_diff.append({**entry, "via": "esdb"})
            elif oxford_ize_ok:
                ok_same += 1
            elif not differ and us_l in info["us"] and exp_gb and exp_gb != us_l:
                # We kept American/Oxford form as both — flag if traditional GB differs
                # and our word_gb is NOT the traditional B form
                if gb_l not in info["gb"]:
                    bad.append(
                        {
                            **entry,
                            "reason": (
                                f"ESDB expects GB {sorted(info['gb'])} / US {sorted(info['us'])}; "
                                f"both columns are {w_gb!r}"
                            ),
                        }
                    )
                else:
                    ok_same += 1
            else:
                reasons = []
                if not differ:
                    reasons.append("word_us == word_gb")
                if not us_ok:
                    reasons.append(f"word_us∉US{sorted(info['us'])[:4]}")
                if not gb_ok:
                    reasons.append(f"word_gb∉GB{sorted(info['gb'])[:4]}")
                bad.append({**entry, "reason": "; ".join(reasons)})
        elif breame_diff:
            if differ and us_l == breame_us:
                ok_diff.append({**entry, "via": "breame", "expected_us": breame_us})
            elif not differ:
                bad.append(
                    {
                        **entry,
                        "expected_us": breame_us,
                        "reason": f"breame expects US {breame_us!r}",
                    }
                )
            else:
                bad.append(
                    {
                        **entry,
                        "expected_us": breame_us,
                        "reason": f"word_us should be {breame_us!r}",
                    }
                )
        else:
            if differ:
                extra.append(
                    {
                        **entry,
                        "reason": "diff without ESDB/breame requirement (hyphen/spacing OK)",
                    }
                )
            else:
                ok_same += 1

    ok_diff = dedupe(ok_diff)
    bad = dedupe(bad)
    extra = dedupe(extra)

    report = {
        "summary": {
            "esdb_pair_forms": len(pairs),
            "rows": len(rows),
            "ok_required_diff": len(ok_diff),
            "bad_missing_or_wrong_diff": len(bad),
            "extra_optional_diffs": len(extra),
            "ok_same": ok_same,
        },
        "bad": bad,
        "extra_diffs": extra,
        "ok_sample": ok_diff[:50],
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "ESDB/SCOWL spelling audit",
        "=" * 40,
        f"Clear A↔B spelling pairs indexed: {len(pairs)}",
        f"OK — required diff present:       {len(ok_diff)}",
        f"BAD — required diff missing/wrong:{len(bad)}",
        f"Extra diffs (hyphen etc.):        {len(extra)}",
        f"OK — same spelling (no split):    {ok_same}",
        "",
        "--- BAD (should have US/GB difference) ---",
    ]
    for it in bad:
        lines.append(
            f"  gb={it['word_gb']!r:20} us={it['word_us']!r:20} [{it['pos']}] "
            f"expected_us={it.get('expected_us')!r} — {it.get('reason')}"
        )
    lines += ["", "--- Extra diffs (usually fine) ---"]
    for it in extra:
        lines.append(f"  {it['word_gb']!r} -> {it['word_us']!r}  [{it['pos']}]")

    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
