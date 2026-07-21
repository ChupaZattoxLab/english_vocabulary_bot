"""
Parse a single OALD definition page into our vocabulary schema.

Adapted from nalgeon/words converters (BeautifulSoup + Entry dataclass),
but targets full entry HTML (#entryContent) instead of wordlist <li>s.

Cases:
  - same spelling (about): word_us == word_gb == headword
  - US variant (colour): headword = GB, `.variants[type=vs] .v` = US

Usage:
    python scripts/parse_oald_entry.py path/to/page.html
    python scripts/parse_oald_entry.py path/to/page.html --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Tag

BASE_URL = "https://www.oxfordlearnersdictionaries.com"


@dataclass
class OaldEntry:
    """Maps onto data/enriched words schema columns."""

    word_us: str
    word_gb: str
    lexical_category: str
    ipa_us: list[str] = field(default_factory=list)
    ipa_gb: list[str] = field(default_factory=list)
    definition: str = ""
    example: str = ""
    audio_source_us: list[str] = field(default_factory=list)
    audio_source_gb: list[str] = field(default_factory=list)
    translations: dict = field(default_factory=dict)
    # extras (not in final CSV schema, useful for enrichment)
    cefr: str = ""
    entry_id: str = ""
    source_url: str = ""


def load_html(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")


def abs_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BASE_URL + url
    return BASE_URL + "/" + url


def text_of(el: Tag | None) -> str:
    if el is None:
        return ""
    return " ".join(el.get_text(" ", strip=True).split())


def parse_phon_block(block: Tag | None) -> tuple[list[str], list[str]]:
    """Return (ipa_list, audio_urls) from .phons_br / .phons_n_am."""
    if block is None:
        return [], []
    ipas: list[str] = []
    for phon in block.select("span.phon"):
        t = text_of(phon)
        if t and t not in ipas:
            ipas.append(t)
    audios: list[str] = []
    for sound in block.select("div.sound.audio_play_button"):
        for attr in ("data-src-ogg", "data-src-mp3"):
            u = abs_url(sound.get(attr))
            if u and u not in audios:
                audios.append(u)
                break
    return ipas, audios


# Spelling-variant labels (type=vs). Not vocabulary synonyms (type=vf).
_US_SPELLING_LABEL = re.compile(
    r"(?:north\s+american(?:\s+english)?|american\s+english|\bus(?:\s+english)?\b)",
    re.I,
)
_INFORMAL_LABEL = re.compile(
    r"\b(?:informal|old-fashioned|slang|rare|dialect|humorous)\b",
    re.I,
)


def looks_like_spelling_variant(a: str, b: str) -> bool:
    """True if a/b look like orthographic US↔GB pairs, not unrelated lemmas."""
    a, b = a.strip().lower(), b.strip().lower()
    if not a or not b or a == b:
        return False
    if " " in a or " " in b:
        return False
    if abs(len(a) - len(b)) > 3:
        return False
    # shared prefix (colour/color, analyse/analyze, grey/gray)
    pref = 0
    for x, y in zip(a, b):
        if x != y:
            break
        pref += 1
    if pref < min(2, min(len(a), len(b)) // 2):
        return False
    from difflib import SequenceMatcher

    if SequenceMatcher(None, a, b).ratio() < 0.72:
        return False
    return True


def is_american_spelling_of(gb: str, candidate: str) -> bool:
    """True if candidate looks like the American orthography of gb."""
    gb, cand = gb.strip().lower(), candidate.strip().lower()
    if not gb or not cand or gb == cand:
        return False
    if " " in gb or " " in cand:
        return False

    # Short / irregular pairs (shared prefix too short for the ratio heuristic)
    irregular = {
        "grey": "gray",
        "tyre": "tire",
        "kerb": "curb",
        "sceptical": "skeptical",
        "disc": "disk",
        "maths": "math",
        "mum": "mom",  # listed for completeness; vf path usually skipped
        "aluminium": "aluminum",
        "manoeuvre": "maneuver",
        "gaol": "jail",
    }
    if irregular.get(gb) == cand:
        return True

    if not looks_like_spelling_variant(gb, cand):
        return False

    # Common GB→US substitutions (candidate must be the US side)
    checks = [
        gb.replace("isation", "ization") == cand,
        gb.replace("isation", "ization").replace("ise", "ize") == cand,
        re.sub(r"ise\b", "ize", gb) == cand,
        re.sub(r"ised\b", "ized", gb) == cand,
        re.sub(r"iser\b", "izer", gb) == cand,
        re.sub(r"ising\b", "izing", gb) == cand,
        gb.replace("our", "or") == cand,
        gb.endswith("re") and gb[:-2] + "er" == cand,
        gb.replace("ogue", "og") == cand,
        gb.replace("ae", "e") == cand,
        gb.replace("oe", "e") == cand,
        gb.replace("ll", "l") == cand and "ll" in gb,
        gb.replace("ence", "ense") == cand,
        gb.replace("amme", "am") == cand,
        re.sub(r"e(?=ment\b)", "", gb) == cand,  # judgement → judgment
        gb == "programme" and cand == "program",
        gb == "jewellery" and cand == "jewelry",
        gb == "metre" and cand == "meter",
        gb == "litre" and cand == "liter",
        gb == "fibre" and cand == "fiber",
        cand == gb + "l" and gb.endswith("l"),  # enrol → enroll
    ]
    if any(checks):
        return True
    # US candidate should not be the traditional -ise form of an -ize headword
    if gb.endswith("ize") and cand.endswith("ise"):
        return False
    if gb.endswith("ization") and cand.endswith("isation"):
        return False
    return False


def parse_us_spelling(webtop: Tag | None, headword: str) -> str:
    """Extract American *spelling* from OALD ``type=vs`` variant blocks.

    OALD markup::
        <div class="variants" type="vs">
          (<span class="v-g">
             <span class="labels">US English</span>
             <span class="v">color</span>
           </span>)
        </div>

    Only ``type=vs`` (spelling). Ignore ``vf`` (vocab: petrol→gas), ``alt``
    (plurals), informal forms (altho), inflection notes, and British
    ``(also organise)`` listed under Oxford ``-ize`` headwords.
    """
    if webtop is None:
        return headword

    for block in webtop.select("div.variants"):
        if (block.get("type") or "").lower() != "vs":
            continue
        block_text = text_of(block)
        if _INFORMAL_LABEL.search(block_text):
            continue

        for vg in block.select("span.v-g, .v-g"):
            labels = text_of(vg.select_one(".labels"))
            variant = text_of(vg.select_one("span.v, .v"))
            if not variant:
                continue
            if _INFORMAL_LABEL.search(labels):
                continue
            # Accept irregular short pairs (tyre/tire) even when prefix heuristic fails
            if not (
                looks_like_spelling_variant(headword, variant)
                or is_american_spelling_of(headword, variant)
            ):
                continue

            labels_l = labels.lower()
            us_marked = bool(_US_SPELLING_LABEL.search(labels_l)) or (
                not labels_l and bool(_US_SPELLING_LABEL.search(block_text))
            )
            also_variant = bool(re.search(r"\balso\b", block_text, re.I))

            if us_marked and is_american_spelling_of(headword, variant):
                return variant
            # "(also endeavor)" with no regional label — accept only US-ward forms
            if (
                also_variant
                and not re.search(r"british", block_text, re.I)
                and is_american_spelling_of(headword, variant)
            ):
                return variant

    top_text = text_of(webtop)
    m = re.search(
        r"\(\s*US\s+English\s+([A-Za-z][A-Za-z0-9'\-]*)\s*\)",
        top_text,
        re.I,
    )
    if m and is_american_spelling_of(headword, m.group(1)):
        return m.group(1)
    return headword


def clean_headword(head: str) -> str:
    """Strip homograph indices that sometimes leak into visible headword text."""
    head = head.strip()
    head = re.sub(r"\s+\d+$", "", head)  # "sake 1" -> "sake"
    return head.strip()


def first_sense(entry: Tag) -> Tag | None:
    """Pick the best sense that actually has a definition.

    Many OALD entries (accordance, behalf, sake, …) exist only as idioms —
    their senses live under div.idioms. Prefer non-idiom senses, then idioms.
    Skip senses with no .def (e.g. upon sense 1 is only a cross-ref).
    """
    candidates: list[tuple[int, Tag]] = []
    for sense in entry.select("li.sense"):
        if sense.select_one("span.def, .def") is None:
            continue
        in_idioms = bool(sense.find_parent("div", class_="idioms"))
        # lower score = better
        candidates.append((1 if in_idioms else 0, sense))
    if not candidates:
        # last resort: any sense
        for sense in entry.select("li.sense"):
            return sense
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def first_phrasal_ref(entry: Tag) -> tuple[str, str] | None:
    """For verb stubs that only list Phrasal Verbs (consist, rely, …).

    Returns (label, absolute_url) for the first phrasal link, or None.
    """
    aside = entry.select_one("aside.phrasal_verb_links")
    if aside is None:
        return None
    link = aside.select_one("a.Ref[href], a[href]")
    if link is None:
        return None
    label = text_of(link.select_one(".xh") or link)
    href = abs_url(link.get("href"))
    if not label or not href:
        return None
    return label, href


def cefr_from_symbol(el: Tag | None) -> str:
    """Read CEFR from ox3ksym_a1 / ox5ksym_b2 class on Oxford key icons."""
    if el is None:
        return ""
    for node in el.select("[class*=ox3ksym_], [class*=ox5ksym_]"):
        for cls in node.get("class", []):
            m = re.search(r"ox[35]ksym_([a-c][12])", cls, re.I)
            if m:
                return m.group(1).lower()
    return ""


def parse_cefr(webtop: Tag | None, sense: Tag | None) -> str:
    """CEFR level for the entry (e.g. a1, b2). Prefer first sense, then webtop."""
    if sense is not None:
        level = (sense.get("cefr") or "").strip().lower()
        if re.fullmatch(r"[a-c][12]", level):
            return level
        level = cefr_from_symbol(sense)
        if level:
            return level
    return cefr_from_symbol(webtop)


def parse_entry(soup: BeautifulSoup, source_url: str = "") -> OaldEntry:
    root = soup.select_one("#entryContent .entry") or soup.select_one(".entry")
    if root is None:
        raise ValueError("No OALD .entry found in HTML")

    webtop = root.select_one(".webtop")
    head = clean_headword(
        text_of(root.select_one("h1.headword, .webtop .headword, .headword"))
    )
    pos = text_of(root.select_one(".webtop .pos, span.pos"))
    entry_id = root.get("id") or ""

    ipa_gb, audio_gb = parse_phon_block(root.select_one(".phons_br"))
    ipa_us, audio_us = parse_phon_block(root.select_one(".phons_n_am"))

    word_gb = head
    word_us = clean_headword(parse_us_spelling(webtop, head))

    sense = first_sense(root)
    definition = ""
    example = ""
    if sense:
        definition = text_of(sense.select_one("span.def, .def"))
        ex = sense.select_one("ul.examples span.x, span.x")
        example = text_of(ex)

    cefr = parse_cefr(webtop, sense)

    return OaldEntry(
        word_us=word_us,
        word_gb=word_gb,
        lexical_category=pos,
        ipa_us=ipa_us,
        ipa_gb=ipa_gb,
        definition=definition,
        example=example,
        audio_source_us=audio_us,
        audio_source_gb=audio_gb,
        translations={},
        cefr=cefr,
        entry_id=entry_id,
        source_url=source_url,
    )


def to_schema_dict(entry: OaldEntry) -> dict:
    """Schema columns (translations optional / empty for OALD-only dataset)."""
    return {
        "word_us": entry.word_us,
        "word_gb": entry.word_gb,
        "lexical_category": entry.lexical_category,
        "cefr": entry.cefr,
        "ipa_us": entry.ipa_us,
        "ipa_gb": entry.ipa_gb,
        "definition": entry.definition,
        "example": entry.example,
        "audio_source_us": entry.audio_source_us,
        "audio_source_gb": entry.audio_source_gb,
        "translations": entry.translations,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("html", type=Path, help="Saved OALD definition page HTML")
    ap.add_argument("--json", action="store_true", help="Print JSON (schema columns)")
    ap.add_argument("--url", default="", help="Optional source URL metadata")
    args = ap.parse_args()

    if not args.html.exists():
        sys.exit(f"File not found: {args.html}")

    soup = load_html(args.html)
    entry = parse_entry(soup, source_url=args.url)
    data = to_schema_dict(entry)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"word_us / word_gb : {data['word_us']} / {data['word_gb']}")
        print(f"lexical_category  : {data['lexical_category']}")
        print(f"cefr              : {data['cefr']}")
        print(f"ipa_gb            : {data['ipa_gb']}")
        print(f"ipa_us            : {data['ipa_us']}")
        print(f"audio_gb          : {data['audio_source_gb']}")
        print(f"audio_us          : {data['audio_source_us']}")
        print(f"definition        : {data['definition'][:120]}")
        print(f"example           : {data['example']}")
        print(f"entry_id (extra)  : {entry.entry_id}")


if __name__ == "__main__":
    main()
