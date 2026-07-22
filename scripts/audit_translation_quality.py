"""Score all RU translations for student-card suitability.

Tiers (student-facing flashcard):
  excellent — short, natural, matches primary modern OALD sense
  ok        — usable but awkward / secondary / dictionary-ish / noisy also
  bad       — wrong sense, meta-junk, broken text, unusable as a card gloss

Usage:
  python scripts/audit_translation_quality.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROWS = json.loads((ROOT / "data" / "oald" / "words.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "oald" / "translation_quality_audit.json"

# Hard bad — only entries still genuinely wrong/unusable after cleaning.
# (Previously listed many that are now curated-correct.)
FORCE_BAD: set[tuple[str, str]] = set()


FORCE_OK: set[tuple[str, str]] = {
    ("a", "indefinite article"),
    ("an", "indefinite article"),
    ("the", "definite article"),
    ("into", "preposition"),
    ("towards", "preposition"),
    ("fish", "verb"),
    ("chance", "noun"),  # случай vs возможность — usable but not ideal
    ("inspire", "verb"),
    ("mortgage", "noun"),
    ("discount", "verb"),
    ("access", "verb"),
    ("replace", "verb"),
    ("vote", "verb"),
    ("absorb", "verb"),
    ("launch", "noun"),
}

META_PREP = re.compile(
    r"указывает на|в пространственном значении|во временном значении|"
    r"передаётся приставк|соединительный союз|противительный союз|"
    r"в сложных словах",
    re.I,
)
BROKEN = re.compile(
    r"(?:вфутах|столкновениескаким|Повреждаемость|согласованность ов |"
    r"фильмав|наносящий ущерб дискредитирующий|слитносчислительным|"
    r"привестивсостояние|ехатьвкарете|перевозитьвкарете|"
    r"относящийсякконгрессу|освещениевпечати|средстваксуществованию|"
    r"вкачестведополнения|всемирнаякомпьютерная|"
    r"формироватьиукомплектовывать|ксчастьюсчастлив|"
    r"вфеноменологии|приведениевпорядок|приводитьвпорядок|"
    r"выстраиватьвлинию|заноситьвкнигу|поломкамеханизма|"
    r"участвоватьвпоходе|имеющийсявраспоряжении|"
    r"отпечатыватьсявпамяти|бытьвсостоянии|входитьвподробности|"
    r"готовитькпечати|получатьсяврезультате|"
    r"относящийсякэволюционизму|относящийсякучреждению|"
    r"занятиявлаборатории|портативныйкомпьютер|"
    r"вводитьвупотребление|находящийсявобращении|"
    r"приведениевсоответствие|единственныйвсвоём|"
    r"находящийсявверхнем|передачавчастную|"
    r"магазинасцелью|ссыпатьвмешок)",
    re.I,
)
EXAMPLEISH = re.compile(r"^(она|он|они|я|мы|вы)\s+\S+", re.I)
LETTERED = re.compile(r"^[абвг]\)", re.I)
ARCHAIC = re.compile(
    r"индосс|бенефиц|феод|обыкновение|передаточн|автофургон|"
    r"брачный союз|дисконтировать|вексел",
    re.I,
)
DICT_RESIDUE = re.compile(
    r"кого-л|чему-л|чего-л|кому-л|чём-л|чем-л|к-н\.|а\)|б\)|в\)",
    re.I,
)
GRAMMAR_LABEL = re.compile(r"артикл|междомет|частица\b|инфинитивн", re.I)


def norm_key(w: str, p: str) -> tuple[str, str]:
    return (w.strip().lower(), p.strip().lower())


FORCE_BAD_N = {norm_key(*k) for k in FORCE_BAD}
FORCE_OK_N = {norm_key(*k) for k in FORCE_OK}


def has_glued(s: str) -> bool:
    if not s:
        return False
    if BROKEN.search(s):
        return True
    # Mueller mush: stuck preposition inside a space-free token
    if " " not in s and re.search(
        r"(?:в|к)(?:печати|печатн|карет|конг|суще|сост|памя|употреб|обращ|"
        r"подроб|эвол|учреж|фоном|компьют|книг|порядок|линию|"
        r"походе|готовн|состоян|распоряд|механизм|своём|верхн|частн)",
        s,
        re.I,
    ):
        return True
    return False


def score(r: dict) -> tuple[str, list[str]]:
    w = (r.get("word_gb") or "").strip()
    pos = (r.get("lexical_category") or "").strip()
    nk = norm_key(w, pos)

    t = (r.get("translations") or {}).get("ru") or {}
    main = (t.get("main") or "").strip()
    also = [str(x).strip() for x in (t.get("also") or []) if x and str(x).strip()]
    blob = main + " | " + " | ".join(also)
    reasons: list[str] = []

    if not main:
        return "bad", ["empty"]

    if nk in FORCE_BAD_N:
        return "bad", ["force_bad"]

    if META_PREP.search(main):
        reasons.append("meta_dictionary")
    if has_glued(main) or BROKEN.search(main):
        reasons.append("broken_text")
    if EXAMPLEISH.search(main):
        reasons.append("example_as_gloss")
    if ARCHAIC.search(main):
        reasons.append("archaic_primary")
    if LETTERED.search(main):
        reasons.append("lettered_sense")

    if nk in FORCE_OK_N:
        # curated: keep as ok even if slightly awkward
        return "ok", ["force_ok"] + reasons

    if any(
        x in reasons
        for x in ("meta_dictionary", "broken_text", "example_as_gloss", "archaic_primary")
    ):
        return "bad", reasons

    # --- ok / excellent ---
    if any(has_glued(x) or BROKEN.search(x) for x in also):
        reasons.append("broken_also")

    words = main.split()
    n_words = len(words)
    n_chars = len(main)

    if GRAMMAR_LABEL.search(main):
        reasons.append("grammar_label")
    if DICT_RESIDUE.search(main) or any(DICT_RESIDUE.search(x) for x in also):
        reasons.append("dict_residue")
    if n_words >= 4 or n_chars >= 28:
        reasons.append("too_long")
    if n_words >= 3 and any(w in main for w in ("или", "либо", "значение", "отношение")):
        reasons.append("dictionary_style")
    if any(has_glued(x) or ARCHAIC.search(x) or len(x) >= 36 or len(x.split()) >= 5 for x in also):
        reasons.append("noisy_also")
    if re.search(r"(.)\1{2,}", main) or main != main.strip():
        reasons.append("typoish")
    # duplicated token in main
    if len(words) >= 2 and words[0].lower() == words[1].lower():
        reasons.append("duplicated")
    # Title Case leftover
    if re.search(r"^[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+", main) and main[0].isupper():
        if sum(1 for ch in main if ch.isupper()) >= 2:
            reasons.append("weird_caps")

    closed = any(
        x in pos.lower()
        for x in (
            "preposition",
            "conjunction",
            "determiner",
            "pronoun",
            "article",
            "modal",
            "infinitive",
        )
    )

    if reasons:
        return "ok", reasons

    if closed:
        if n_words <= 3 and n_chars <= 24:
            return "excellent", ["clean_function_word"]
        return "ok", ["function_word_long"]

    if n_words <= 2 and n_chars <= 20:
        return "excellent", ["short_natural"]
    if n_words == 3 and n_chars <= 24:
        return "excellent", ["short_phrase"]
    return "ok", ["borderline_length"]


def main() -> None:
    buckets: dict[str, list[dict]] = {"excellent": [], "ok": [], "bad": []}
    reason_counts: Counter[str] = Counter()
    pos_tier: dict[str, Counter[str]] = {
        "excellent": Counter(),
        "ok": Counter(),
        "bad": Counter(),
    }

    for r in ROWS:
        tier, reasons = score(r)
        for reason in reasons:
            reason_counts[reason] += 1
        item = {
            "word": r.get("word_gb"),
            "pos": r.get("lexical_category"),
            "cefr": r.get("cefr") or "",
            "main": (r.get("translations") or {}).get("ru", {}).get("main"),
            "also": (r.get("translations") or {}).get("ru", {}).get("also") or [],
            "definition": (r.get("definition") or "")[:140],
            "reasons": reasons,
            "tier": tier,
        }
        buckets[tier].append(item)
        pos_tier[tier][(r.get("lexical_category") or "").split(",")[0].strip()] += 1

    # spot-check caveat: among short "excellent", expect residual wrong senses
    summary = {
        "total": len(ROWS),
        "counts": {k: len(v) for k, v in buckets.items()},
        "pct": {
            k: round(100 * len(v) / max(len(ROWS), 1), 1) for k, v in buckets.items()
        },
        "caveat": (
            "excellent = form looks student-ready; random manual spot-check of short "
            "glosses still finds ~8–12% wrong/secondary sense vs OALD primary definition. "
            "Treat excellent as upper bound."
        ),
        "top_reasons": reason_counts.most_common(30),
        "bad_by_pos": pos_tier["bad"].most_common(15),
        "ok_by_pos": pos_tier["ok"].most_common(15),
        "rubric": {
            "excellent": "короткий естественный глянец под главный современный смысл",
            "ok": "можно показать, но коряво / вторичный смысл / шум в also / словарь",
            "bad": "нельзя на карточку: неверный смысл, мета-словарь, битый текст",
        },
        "bad": buckets["bad"],
        "ok": buckets["ok"],
        "excellent_sample": buckets["excellent"][:60],
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"total={summary['total']} "
        f"excellent={summary['counts']['excellent']} "
        f"ok={summary['counts']['ok']} "
        f"bad={summary['counts']['bad']}"
    )
    print("pct", summary["pct"])
    print("bad:")
    for x in buckets["bad"]:
        print(f"  {x['word']:16} {str(x['pos'])[:22]:22} {x['main']}")


if __name__ == "__main__":
    main()
