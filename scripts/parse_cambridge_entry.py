"""
Parse a Cambridge Dictionary English entry page (CALD / AMP HTML).

Prefer CALD block (data-id=cald4). Pull first usable definition + example,
CEFR from .epp-xref.dxref when present.

Usage:
    python scripts/parse_cambridge_entry.py path/to/page.html
    python scripts/parse_cambridge_entry.py path/to/page.html --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Tag


@dataclass
class CambridgeSense:
    word: str
    lexical_category: str
    cefr: str
    definition: str
    example: str
    phrase_title: str = ""


def load_html(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")


def text_of(el: Tag | None) -> str:
    if el is None:
        return ""
    text = " ".join(el.get_text(" ", strip=True).split())
    # Cambridge wraps linked words in <a>, which leaves "word ," gaps
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def preferred_dict_block(soup: BeautifulSoup) -> Tag | None:
    """Prefer Advanced Learner's (cald4), else first .dictionary with defs."""
    page = soup.select_one("#page-content, article#page-content, .page")
    root = page or soup
    cald = root.select_one('.dictionary[data-id="cald4"], #dataset_cald4')
    if cald is not None:
        block = cald if cald.select_one(".def, .ddef_d") else cald.find_parent(
            "div", class_="dictionary"
        )
        if block is not None and block.select_one(".def, .ddef_d"):
            return block
        # #dataset_cald4 is often an empty anchor — parent panel holds content
        panel = root.select_one('.dictionary[data-id="cald4"]')
        if panel is not None:
            return panel
    for block in root.select("div.dictionary"):
        if block.select_one(".def.ddef_d, .ddef_d, span.def, .def"):
            return block
    return root


def is_weak_example(example: str, headword: str = "") -> bool:
    """Reject Cambridge list-style examples (common for numbers)."""
    ex = example.strip()
    if not ex:
        return True
    # "twenty-nine, thirty, thirty-one"
    if ex.count(",") >= 2 and len(ex) < 80:
        return True
    if re.fullmatch(r"[\d\s,\-–—and]+", ex, re.I):
        return True
    # bare number / short fragment
    if len(ex.split()) < 3 and not re.search(r"[.!?]", ex):
        hw = headword.strip().lower()
        if hw.isdigit() or re.fullmatch(r"(thirteen|fourteen|fifteen|sixteen|seventeen|"
                                         r"eighteen|nineteen|twenty|thirty|forty|fifty|"
                                         r"sixty|seventy|eighty|ninety|thousand|trillion|"
                                         r"hundred|million|billion)", hw):
            return True
    return False


def collect_examples(block: Tag) -> list[str]:
    out: list[str] = []
    for eg in block.select(".examp .eg, .eg.deg, span.eg, span.deg"):
        t = text_of(eg)
        if t and t not in out:
            out.append(t)
    return out


def parse_entry(soup: BeautifulSoup, prefer_pos: str = "") -> CambridgeSense:
    block = preferred_dict_block(soup)
    if block is None:
        raise ValueError("No Cambridge dictionary block found")

    word = text_of(block.select_one(".hw.dhw, span.hw, .headword .hw, h1.ti b"))
    if not word:
        word = text_of(soup.select_one("h1.ti b, h1 .tb"))

    prefer = prefer_pos.strip().lower()
    def_blocks = block.select(".def-block.ddef_block, .ddef_block")
    if not def_blocks:
        def_blocks = block.select(".def.ddef_d, .ddef_d")

    best: Tag | None = None
    best_score = 10**9
    for db in def_blocks:
        # climb to entry-body__el for POS
        el = db.find_parent("div", class_="entry-body__el") or db
        pos = text_of(el.select_one(".pos.dpos, span.pos")).lower()
        has_def = bool(text_of(db.select_one(".def.ddef_d, .ddef_d, .def")))
        if not has_def:
            continue
        score = 0
        if prefer and pos and prefer not in pos and pos not in prefer:
            score += 5
        # prefer non-business / non-american secondary datasets less
        parent_dict = db.find_parent("div", class_="dictionary")
        did = (parent_dict.get("data-id") if parent_dict else "") or ""
        if did and did != "cald4":
            score += 2
        # prefer blocks that have a usable example
        ex = text_of(db.select_one(".examp .eg, .eg.deg, span.eg"))
        if not ex or is_weak_example(ex, word):
            score += 1
        if score < best_score:
            best_score = score
            best = db

    if best is None:
        # phrase-only: definition still under .def
        best = block.select_one(".def.ddef_d, .ddef_d")

    if best is None:
        raise ValueError("No Cambridge definition found")

    def_el = best if best.name and "def" in (best.get("class") or []) else best.select_one(
        ".def.ddef_d, .ddef_d, .def"
    )
    definition = text_of(def_el)
    # strip trailing colon common on Cambridge
    definition = definition.rstrip(": ").strip()

    example = ""
    # Prefer example from best sense, else any strong example on the page
    candidates = collect_examples(best if hasattr(best, "select") else block)
    if best is not None and best is not block:
        # also scan whole preferred dictionary block
        for t in collect_examples(block):
            if t not in candidates:
                candidates.append(t)
    for t in candidates:
        if not is_weak_example(t, word):
            example = t
            break
    if not example and candidates:
        example = candidates[0]

    cefr = ""
    xref = best.select_one(".epp-xref.dxref, .dxref")
    if xref is not None:
        m = re.search(r"\b([A-C][12])\b", text_of(xref), re.I)
        if m:
            cefr = m.group(1).lower()

    el = best.find_parent("div", class_="entry-body__el") or block
    pos = text_of(el.select_one(".pos.dpos, span.pos"))
    phrase = ""
    pb = best.find_parent("div", class_="phrase-block")
    if pb is not None:
        phrase = text_of(pb.select_one(".phrase-title, .dphrase-title"))

    return CambridgeSense(
        word=word,
        lexical_category=pos,
        cefr=cefr,
        definition=definition,
        example=example,
        phrase_title=phrase,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("html", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pos", default="", help="Prefer this POS when multiple senses")
    args = ap.parse_args()
    if not args.html.exists():
        sys.exit(f"File not found: {args.html}")
    sense = parse_entry(load_html(args.html), prefer_pos=args.pos)
    data = {
        "word": sense.word,
        "lexical_category": sense.lexical_category,
        "cefr": sense.cefr,
        "definition": sense.definition,
        "example": sense.example,
        "phrase_title": sense.phrase_title,
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for k, v in data.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
