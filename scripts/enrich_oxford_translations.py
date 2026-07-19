"""Oxford Dictionaries Translations API → EN→RU enrichment sketch.

Docs:
  GET /api/v2/translations/{source}/{target}/{word}
  https://developer.oxforddictionaries.com/translations-api

Auth (headers):
  app_id, app_key   — from https://developer.oxforddictionaries.com/

Env:
  OXFORD_APP_ID
  OXFORD_APP_KEY

Usage:
  # dry-run: show plan, no HTTP
  python scripts/enrich_oxford_translations.py --dry-run

  # fetch unique words (resumable via cache)
  python scripts/enrich_oxford_translations.py

  # limit for sandbox testing (500 calls/day on free tier — check current limits)
  python scripts/enrich_oxford_translations.py --limit 20

Priority (matches our dataset policy):
  1. Oxford Translations API (sense + POS aware)
  2. leave empty if missing — fill later (Mueller / kaikki / Yandex)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_CSV = ROOT / "data" / "enriched" / "words.csv"
OUT_CSV = ROOT / "data" / "enriched" / "words_with_ru.csv"
OUT_JSON = ROOT / "data" / "enriched" / "words_with_ru.json"
OUT_META = ROOT / "data" / "enriched" / "translations_meta.json"
CACHE_DIR = ROOT / "source" / "oxford_api" / "translations_en_ru"

DEFAULT_BASE = "https://od-api-sandbox.oxforddictionaries.com/api/v2"
SOURCE_LANG = "en"
TARGET_LANG = "ru"

# Oxford lexicalCategory.id → our dataset pos
POS_MAP: dict[str, set[str]] = {
    "noun": {"noun"},
    "verb": {"verb", "modal verb", "auxiliary verb", "linking verb"},
    "adjective": {"adjective"},
    "adverb": {"adverb"},
    "preposition": {"preposition"},
    "conjunction": {"conjunction"},
    "pronoun": {"pronoun"},
    "determiner": {"determiner", "indefinite article", "definite article"},
    "interjection": {"exclamation"},
    "numeral": {"number", "ordinal number"},
    "residual": set(),  # catch-all, never preferred
}


def load_dotenv() -> None:
    """Load KEY=VALUE from repo .env if present (does not override existing env)."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_credentials() -> tuple[str, str]:
    load_dotenv()
    app_id = os.environ.get("OXFORD_APP_ID", "").strip()
    app_key = os.environ.get("OXFORD_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise SystemExit(
            "Set OXFORD_APP_ID and OXFORD_APP_KEY env vars "
            "(Oxford Dictionaries API developer portal)."
        )
    return app_id, app_key


def cache_path(word: str) -> Path:
    return CACHE_DIR / f"{urllib.parse.quote(word.lower(), safe='')}.json"


def get_base() -> str:
    load_dotenv()
    return os.environ.get("OXFORD_API_BASE", DEFAULT_BASE).rstrip("/")


def api_get(
    path: str,
    app_id: str,
    app_key: str,
    budget: list[int] | None = None,
) -> tuple[int, dict | None]:
    """budget is mutable [used, max]; raises StopIteration-style via special status."""
    if budget is not None and budget[0] >= budget[1]:
        return 429, {"error": "local call budget exhausted"}
    url = f"{get_base()}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "app_id": app_id,
            "app_key": app_key,
            "User-Agent": "english-vocabulary-bot/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if budget is not None:
                budget[0] += 1
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if budget is not None:
            budget[0] += 1  # failed calls usually still count
        body = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            payload = {"error": body[:300]}
        return e.code, payload


def fetch_translations(
    word: str,
    app_id: str,
    app_key: str,
    force: bool = False,
    budget: list[int] | None = None,
    use_search: bool = False,
) -> dict:
    """Cache wrapper around Translations endpoint (known headword)."""
    path = cache_path(word)
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))

    if budget is not None and budget[0] >= budget[1]:
        return {
            "query": word,
            "resolved": None,
            "status": 429,
            "ok": False,
            "data": None,
            "skipped": "budget",
        }

    # headwords only — phrases like "have to" may 404
    status, data = api_get(
        f"/translations/{SOURCE_LANG}/{TARGET_LANG}/{urllib.parse.quote(word.lower())}",
        app_id,
        app_key,
        budget=budget,
    )

    if status == 404 and use_search and (budget is None or budget[0] < budget[1] - 1):
        # Flow A step 1: resolve via search (costs extra calls — off by default near quota)
        s_status, s_data = api_get(
            f"/search/translations/{SOURCE_LANG}/{TARGET_LANG}"
            f"?q={urllib.parse.quote(word)}&limit=5",
            app_id,
            app_key,
            budget=budget,
        )
        headword = None
        if s_status == 200 and s_data:
            results = s_data.get("results") or []
            if results:
                headword = results[0].get("id") or results[0].get("word")
        if headword and headword.lower() != word.lower():
            status, data = api_get(
                f"/translations/{SOURCE_LANG}/{TARGET_LANG}/{urllib.parse.quote(headword)}",
                app_id,
                app_key,
                budget=budget,
            )
            result = {
                "query": word,
                "resolved": headword,
                "status": status,
                "ok": status == 200,
                "data": data,
            }
        else:
            result = {
                "query": word,
                "resolved": None,
                "status": 404,
                "ok": False,
                "data": data,
                "search": s_data,
            }
    elif status == 404:
        result = {
            "query": word,
            "resolved": None,
            "status": 404,
            "ok": False,
            "data": data,
        }
    else:
        result = {
            "query": word,
            "resolved": word,
            "status": status,
            "ok": status == 200,
            "data": data,
        }

    # cache successes and definitive 404s; retry transient errors later
    if result["ok"] or result["status"] == 404:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _norm_pos(p: str) -> str:
    return (p or "").strip().lower()


def pick_translations(payload: dict | None, oxford_pos: str, max_items: int = 3) -> list[str]:
    """Pick RU glosses preferring senses whose lexicalCategory matches our POS."""
    if not payload:
        return []

    wanted = set()
    op = _norm_pos(oxford_pos)
    for api_pos, ours in POS_MAP.items():
        if op in ours or op == api_pos:
            wanted.add(api_pos)

    matched: list[str] = []
    fallback: list[str] = []

    for result in payload.get("results") or []:
        for lex in result.get("lexicalEntries") or []:
            cat = ((lex.get("lexicalCategory") or {}).get("id") or "").lower()
            bucket = matched if (not wanted or cat in wanted) else fallback
            for entry in lex.get("entries") or []:
                for sense in entry.get("senses") or []:
                    for tr in sense.get("translations") or []:
                        if (tr.get("language") or "").lower() not in ("ru", "russian", ""):
                            # some payloads omit language when endpoint is already en/ru
                            text = (tr.get("text") or "").strip()
                            if text and text not in bucket:
                                bucket.append(text)
                            continue
                        text = (tr.get("text") or "").strip()
                        if text and text not in bucket:
                            bucket.append(text)
                    # nested subsenses
                    for sub in sense.get("subsenses") or []:
                        for tr in sub.get("translations") or []:
                            text = (tr.get("text") or "").strip()
                            if text and text not in bucket:
                                bucket.append(text)

    chosen = matched or fallback
    return chosen[:max_items]


def load_rows() -> list[dict]:
    with IN_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no API calls")
    parser.add_argument("--limit", type=int, default=0, help="Max unique words to process")
    parser.add_argument(
        "--max-calls",
        type=int,
        default=450,
        help="Max NEW API HTTP calls this run (sandbox ~500 total). Default 450.",
    )
    parser.add_argument("--sleep", type=float, default=0.25, help="Delay between API calls")
    parser.add_argument("--force", action="store_true", help="Refetch even if cached")
    parser.add_argument(
        "--use-search",
        action="store_true",
        help="On 404, call Search Translations (uses extra quota)",
    )
    args = parser.parse_args()

    rows = load_rows()
    unique_words = sorted({r["word"] for r in rows}, key=str.lower)
    if args.limit:
        unique_words = unique_words[: args.limit]

    already = sum(1 for w in unique_words if cache_path(w).exists())
    print(f"Rows: {len(rows)}")
    print(f"Unique words to resolve: {len(unique_words)} (cached={already})")
    print(f"Endpoint: {get_base()}/translations/{SOURCE_LANG}/{TARGET_LANG}/{{word}}")
    print(f"Cache: {CACHE_DIR}")
    print(f"Max new API calls this run: {args.max_calls}")

    if args.dry_run:
        sample = unique_words[:10]
        print("Dry-run sample queries:")
        for w in sample:
            print(f"  GET .../translations/en/ru/{urllib.parse.quote(w.lower())}")
        print("Set OXFORD_APP_ID / OXFORD_APP_KEY and re-run without --dry-run.")
        return

    app_id, app_key = load_credentials()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    budget = [0, args.max_calls]  # [used, max]
    api_by_word: dict[str, dict] = {}
    stats = Counter()

    for i, word in enumerate(unique_words, 1):
        cached = cache_path(word).exists() and not args.force
        if not cached and budget[0] >= budget[1]:
            stats["budget_stop"] += 1
            print(
                f"Budget exhausted after {budget[0]} calls at word #{i} ({word!r}). Stopping fetch.",
                flush=True,
            )
            break

        result = fetch_translations(
            word,
            app_id,
            app_key,
            force=args.force,
            budget=budget,
            use_search=args.use_search,
        )
        api_by_word[word] = result
        if result.get("ok"):
            stats["ok"] += 1
        elif result.get("status") == 404:
            stats["not_found"] += 1
        elif result.get("status") == 429 or result.get("skipped") == "budget":
            stats["budget_stop"] += 1
            print(f"Budget stop at {word!r}", flush=True)
            break
        else:
            stats["error"] += 1
            # If auth/rate-limit from server, stop
            if result.get("status") in (401, 403, 429):
                print(f"API {result.get('status')} — stopping.", flush=True)
                break

        if i % 25 == 0 or i == len(unique_words):
            print(
                f"[{i}/{len(unique_words)}] ok={stats['ok']} "
                f"404={stats['not_found']} err={stats['error']} "
                f"calls={budget[0]}/{budget[1]} cached={cached}",
                flush=True,
            )
        if not cached:
            time.sleep(args.sleep)

    # Attach translations using ALL cache (not only this run)
    out_rows: list[dict] = []
    fill = Counter()
    for row in rows:
        word = row["word"]
        api = api_by_word.get(word)
        if api is None and cache_path(word).exists():
            api = json.loads(cache_path(word).read_text(encoding="utf-8"))
        translations: list[str] = []
        if api and api.get("ok"):
            translations = pick_translations(api.get("data"), row["pos"])
        new = dict(row)
        new["translation_ru"] = "; ".join(translations) if translations else ""
        new["translation_source"] = "oxford_api" if translations else ""
        if translations:
            fill["with_translation"] += 1
        else:
            fill["without_translation"] += 1
        out_rows.append(new)

    fields = list(out_rows[0].keys())
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    OUT_JSON.write_text(
        json.dumps(out_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    cached_total = len(list(CACHE_DIR.glob("*.json"))) if CACHE_DIR.exists() else 0
    meta = {
        "endpoint": f"{get_base()}/translations/{SOURCE_LANG}/{TARGET_LANG}/{{word}}",
        "unique_processed_this_run": len(api_by_word),
        "api_calls_this_run": budget[0],
        "api_stats": dict(stats),
        "cache_files": cached_total,
        "row_stats": dict(fill),
        "coverage_pct": round(100 * fill["with_translation"] / max(len(out_rows), 1), 1),
        "outputs": {
            "csv": str(OUT_CSV.relative_to(ROOT)).replace("\\", "/"),
            "json": str(OUT_JSON.relative_to(ROOT)).replace("\\", "/"),
        },
        "next": [
            "Fill remaining gaps via Mueller dict / kaikki translations / Yandex Dictionary",
            "Manually curate phrases: have to, used to, according to",
        ],
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Wrote", OUT_CSV)
    print("Coverage:", meta["coverage_pct"], "%")
    print("API calls this run:", budget[0])
    print("Cache files:", cached_total)
    print("API stats:", dict(stats))


if __name__ == "__main__":
    main()
