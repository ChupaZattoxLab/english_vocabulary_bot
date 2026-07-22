"""Lexicon also→main: realign to English headword's primary student sense.

For every OALD entry: if main does not match the expected RU sense of the
English headword, but one of `also` does — and that gloss is short enough
for a flashcard — promote also→main.

This is intentionally high-precision (desired-sense patterns only). Expand
HEADWORD_RU to cover more lemmas as you audit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Desired primary RU sense only (wrong Mueller senses must NOT match).
HEADWORD_RU: dict[str, str] = {
    "accept": r"принима",
    "administer": r"управл|администрир",
    "administrator": r"администратор|управля",
    "alcohol": r"алкогол|спиртн",
    "alcoholic": r"алкогольн",
    "amateur": r"любител",
    "apartment": r"квартир",
    "applaud": r"аплод|рукоплеск",
    "arm": r"вооруж",
    "arrive": r"прибыв|приезж",
    "ask": r"спрашив|вопрос",
    "asleep": r"спящ",
    "baby": r"ребён|ребен|малыш|младен",
    "balloon": r"шар",
    "bank": r"банк",
    "bat": r"бит",
    "beef": r"говядин",
    "beer": r"пив",
    "black": r"чёрн|черн",
    "blood": r"кров",
    "book": r"книг",
    "borrow": r"заим|одалжива|брать на время",
    "bow": r"поклон|кланя",
    "brown": r"коричнев",
    "brush": r"щётк|щетк",
    "bus": r"автобус",
    "car": r"машин|автомоб",
    "child": r"ребён|ребен|малыш|младен",
    "chip": r"чипс",
    "clean": r"чист",
    "closely": r"близк",
    "club": r"клуб",
    "colour": r"цвет",
    "color": r"цвет",
    "connect": r"связ|соеди",
    "consent": r"соглаш",
    "conservation": r"сохране|охран|защит",
    "constitution": r"конституц",
    "contain": r"содерж",
    "continue": r"продолж",
    "country": r"стран",
    "create": r"созда",
    "crime": r"преступл",
    "curriculum": r"учебн",
    "dance": r"танц",
    "dawn": r"рассвет",
    "decade": r"десятилети",
    "decrease": r"уменьш|сниж",
    "discuss": r"обсужд",
    "discussion": r"обсужд",
    "dog": r"собак",
    "dollar": r"доллар",
    "draft": r"черновик",
    "duration": r"продолжительн",
    "earnings": r"заработ|зарплат|доход",
    "employer": r"работодател",
    "enjoy": r"наслажд|нрав",
    "exist": r"существов",
    "eye": r"глаз",
    "family": r"семь",
    "fan": r"фанат|болельщ",
    "fight": r"сраж|бор",
    "file": r"папк|файл",
    "finish": r"заверш|заканч|окончан",
    "flat": r"квартир|плоск",
    "flood": r"наводн",
    "headache": r"головн.*боль|боль.*голов",
    "healthy": r"здоров",
    "hide": r"прят|скрыв",
    "hope": r"надежд",
    "ill": r"нездоров|больн|хвора",
    "increase": r"увелич",
    "interest": r"интерес",
    "jam": r"варень|джем",
    "job": r"работ",
    "judicial": r"судебн",
    "kick": r"пина|пинок|удар",
    "kill": r"уби",
    "lead": r"вест|лидер",
    "leave": r"покид|остав",
    "letter": r"письм",
    "light": r"бледн|свет",
    "live": r"жить|эфир",
    "love": r"люб",
    "mail": r"почт",
    "match": r"матч",
    "mate": r"товарищ|друг|приятел",
    "meat": r"мяс",
    "milk": r"молок",
    "music": r"музык",
    "musical": r"музыкальн",
    "nail": r"ногт",
    "name": r"имя|назван|назыв",
    "near": r"близк|рядом",
    "nod": r"кива",
    "object": r"предмет|возраж",
    "open": r"откры",
    "organ": r"орган",
    "pale": r"бледн",
    "palm": r"пальм",
    "park": r"парков|парк",
    "party": r"вечеринк",
    "pink": r"розов",
    "plant": r"растен",
    "police": r"полиц",
    "prayer": r"молитв",
    "prefer": r"предпочит",
    "present": r"представ|подарок|текущ",
    "produce": r"производ|выпуска",
    "punch": r"удар|бить|кулак",
    "purple": r"фиолетов|пурпур",
    "question": r"вопрос",
    "reader": r"читател",
    "red": r"красн|алый",
    "refuse": r"отказ",
    "return": r"возвращ",
    "sale": r"продаж",
    "seal": r"печат|пломб",
    "season": r"сезон|время года",
    "send": r"посыл|отправл",
    "sentence": r"предлож",
    "shop": r"магазин",
    "shut": r"закры",
    "signature": r"подпис",
    "singer": r"певец|певиц",
    "sink": r"тону|раковин",
    "sit": r"сид",
    "song": r"песн",
    "sound": r"звук",
    "space": r"космос",
    "span": r"период|промежут|время",
    "sport": r"спорт",
    "sporting": r"спортивн",
    "spot": r"замеча",
    "spring": r"весн",
    "staff": r"персонал|сотрудник|штат",
    "star": r"играть|звезд",
    "start": r"нач",
    "stop": r"останов",
    "student": r"студент|ученик",
    "support": r"поддерж",
    "table": r"стол",
    "talk": r"говор|разговор|бесед",
    "tent": r"палатк",
    "train": r"тренир|обуча|поезд",
    "travel": r"путешеств",
    "tree": r"дерев",
    "universe": r"вселенн|космос",
    "verify": r"провер",
    "visit": r"посещ",
    "wait": r"ожид",
    "walk": r"ход|пеш|гуля|ходьб",
    "warehouse": r"склад",
    "watch": r"смотр|наблюд|часы",
    "wave": r"волн",
    "weather": r"погод",
    "wind": r"извив|вить|наматыв|ветер",
    "wood": r"дерев|древес",
    "wooden": r"деревянн",
    "worker": r"работник|рабоч",
    "yard": r"двор",
}


def matches(pattern: str, gloss: str) -> bool:
    return bool(re.search(pattern, gloss, re.I))


def student_ok(alt: str, main: str) -> bool:
    if re.search(r"^(?:а\)|б\)|в\))", alt):
        return False
    if re.search(
        r"относящ|в выражениях|игорный дом|военно-морской|подневольный|"
        r"организационные мероприятия|осветительная аппаратура|"
        r"философский подход|находящийся рядом предмет",
        alt,
        re.I,
    ):
        return False
    if " " not in alt and re.search(r"[а-яё]{4,}(?:в|к|с|и|по)[а-яё]{4,}", alt, re.I):
        return False
    if len(alt) > 24:
        return False
    if len(alt.split()) >= 4:
        return False
    if len(alt) > len(main) + 10 and len(main.split()) <= 2:
        return False
    return True


def promote_by_lexicon(
    word: str, main: str, also: list[str], definition: str = ""
) -> tuple[str, list[str]]:
    """Promote also→main when also matches headword primary sense and main does not."""
    del definition  # reserved for future def-lemma scoring
    if not word or not main or not also:
        return main, also
    pat = HEADWORD_RU.get(word.lower().strip())
    if not pat or matches(pat, main):
        return main, also
    for alt in also:
        if matches(pat, alt) and student_ok(alt, main):
            rest = [main] + [x for x in also if x.casefold() != alt.casefold()]
            return alt, rest[:2]
    return main, also


def scan_all(rows: list[dict] | None = None) -> list[dict]:
    if rows is None:
        rows = json.loads((ROOT / "data/oald/words.json").read_text(encoding="utf-8"))
    cands = []
    for r in rows:
        tr = (r.get("translations") or {}).get("ru") or {}
        main = tr.get("main") or ""
        also = list(tr.get("also") or [])
        word = (r.get("word_gb") or "").strip()
        if not main or not also:
            continue
        new_main, _ = promote_by_lexicon(word, main, also, r.get("definition") or "")
        if new_main.casefold() != main.casefold():
            cands.append(
                {
                    "word": word,
                    "pos": r.get("lexical_category"),
                    "main": main,
                    "promote": new_main,
                    "also": also,
                    "def": (r.get("definition") or "")[:90],
                }
            )
    return cands


if __name__ == "__main__":
    cands = scan_all()
    out = ROOT / "data" / "oald" / "lex_promote_candidates.json"
    out.write_text(json.dumps(cands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    covered = len(HEADWORD_RU)
    print(f"HEADWORD_RU={covered} realignments={len(cands)} -> {out}")
    for c in cands:
        print(f"{c['word']:14} {str(c['pos'])[:12]:12} {c['main']!r:22} -> {c['promote']!r}")
