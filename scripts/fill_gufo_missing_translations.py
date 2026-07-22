"""Fill missing OALD translations from gufo.me (sense 1) only).

Uses search → prefers /dict/enru_full/{lemma}, falls back to other enru_* /
computer_terms. Takes only the first numbered sense ``1) …`` as the most
popular translation (user request).

Usage:
  python scripts/fill_gufo_missing_translations.py
  python scripts/fill_gufo_missing_translations.py --sleep 1.2 --limit 50
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "oald"
JSON_PATH = OUT / "words.json"
CSV_PATH = OUT / "words.csv"
META_PATH = OUT / "meta.json"

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

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.8",
}


def http_get(url: str, retries: int = 5, sleep: float = 1.0) -> str:
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                time.sleep(sleep * (2 + i * 2))
                continue
            if e.code == 404:
                raise
            time.sleep(sleep * (i + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(sleep * (i + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


def search_links(word: str) -> list[str]:
    html = http_get("https://gufo.me/search?term=" + urllib.parse.quote(word))
    links = re.findall(r'href="(/dict/[^"]+)"', html)
    slug = word.strip().lower().replace(" ", "_")
    scored: list[tuple[int, str]] = []
    for link in links:
        low = link.lower()
        # exact article for this lemma
        leaf = urllib.parse.unquote(low.rsplit("/", 1)[-1])
        score = 0
        if leaf == slug or leaf == word.lower():
            score += 20
        if "/enru_full/" in low:
            score += 8
        elif "/enru_muller/" in low:
            score += 5
        elif re.search(r"/enru_[a-z]+/", low):
            score += 3
        elif "/computer_terms/" in low:
            score += 2
        if score:
            scored.append((score, link))
    scored.sort(key=lambda t: (-t[0], t[1]))
    out: list[str] = []
    seen: set[str] = set()
    for _, link in scored:
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def article_plain(path: str) -> str:
    html = http_get("https://gufo.me" + path)
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    m = re.search(r"<article[^>]*>(.*?)</article>", text, re.S | re.I)
    body = m.group(1) if m else text
    plain = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", plain).strip()


def split_ru(chunk: str) -> list[str]:
    chunk = re.sub(r"\([^)]*\)", "", chunk)
    chunk = re.sub(r"\[[^\]]*\]", "", chunk)
    # cut trailing English example runs
    chunk = re.split(r"\s+[A-Za-z][A-Za-z0-9'\-]*(?:\s+[A-Za-z][A-Za-z0-9'\-]*){1,}", chunk)[0]
    chunk = chunk.strip(" ;,.—–-\"'«»")
    out: list[str] = []
    for part in re.split(r"[,;]", chunk):
        part = part.strip(" ;,.—–-\"'«»")
        part = re.sub(r"^(сущ\.|гл\.|прил\.|нареч\.|I+|II+|III+)\s*", "", part, flags=re.I)
        part = part.strip()
        if not part or len(part) > 70:
            continue
        if part.lower().startswith("сокр"):
            continue
        cyr = len(re.findall(r"[А-Яа-яЁё]", part))
        lat = len(re.findall(r"[A-Za-z]", part))
        if cyr >= 2 and cyr >= lat:
            if part not in out:
                out.append(part)
    return out


def first_sense_ru(plain: str) -> list[str]:
    """Most popular translation = numbered sense 1)."""
    m = re.search(
        r"\b1\)\s*(.+?)(?=\s*(?:[2-9]|\d{2})\)|\s*Источник:|$)",
        plain,
    )
    if m:
        return split_ru(m.group(1))

    # No numbers (e.g. computer_terms): take short RU definition lines
    chunk = plain.split("Источник:")[0]
    chunk = re.sub(r"^[A-Za-z][A-Za-z0-9'\-]*\s*", "", chunk)
    chunk = re.sub(r"\[[^\]]+\]\s*", "", chunk)
    # drop domain tags like Интернет
    chunk = re.sub(
        r"\b(Интернет|Программирование|Онлайновый журнал)\b",
        lambda m: m.group(0) if "журнал" in m.group(0).lower() else " ",
        chunk,
    )
    return split_ru(chunk)


def gufo_translations(word: str) -> tuple[list[str], str]:
    links = search_links(word)
    for link in links[:4]:
        try:
            plain = article_plain(link)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        glosses = first_sense_ru(plain)
        if glosses:
            return glosses, link
    return [], ""


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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    missing_idx = [
        i
        for i, r in enumerate(rows)
        if not ((r.get("translations") or {}).get("ru") or [])
    ]
    if args.limit:
        missing_idx = missing_idx[: args.limit]

    print(f"missing to fill: {len(missing_idx)}", flush=True)
    filled = 0
    failed: list[dict] = []

    for n, i in enumerate(missing_idx, 1):
        r = rows[i]
        word = r["word_gb"]
        time.sleep(args.sleep)
        try:
            glosses, link = gufo_translations(word)
        except Exception as e:  # noqa: BLE001
            failed.append({"word": word, "error": str(e)[:120]})
            print(f"[{n}/{len(missing_idx)}] FAIL {word}: {e}", flush=True)
            continue
        if glosses:
            r["translations"] = {"ru": glosses, "source": "gufo", "gufo_path": link}
            # keep schema shape: only {ru: [...]} in stored field; stash meta separately
            r["translations"] = {"ru": glosses}
            filled += 1
            print(
                f"[{n}/{len(missing_idx)}] OK {word} -> {glosses[:4]} ({link})",
                flush=True,
            )
        else:
            failed.append({"word": word, "error": "no gloss"})
            print(f"[{n}/{len(missing_idx)}] EMPTY {word}", flush=True)

    write_outputs(rows)

    with_ru = sum(
        1 for r in rows if ((r.get("translations") or {}).get("ru") or [])
    )
    meta = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    meta.setdefault("translations", {})
    meta["translations"]["gufo_fill"] = {
        "attempted": len(missing_idx),
        "filled": filled,
        "failed": len(failed),
        "failed_samples": failed[:30],
        "note": "Gufo enru_full sense 1) as most popular translation",
        "site": "https://gufo.me/",
    }
    meta["translations"]["with_ru"] = with_ru
    meta["translations"]["coverage_pct"] = round(100 * with_ru / max(len(rows), 1), 1)
    if "counts" in meta:
        meta["counts"]["with_translations_ru"] = with_ru
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"done filled={filled}/{len(missing_idx)} "
        f"total_with_ru={with_ru}/{len(rows)} "
        f"({meta['translations']['coverage_pct']}%)",
        flush=True,
    )


if __name__ == "__main__":
    main()
