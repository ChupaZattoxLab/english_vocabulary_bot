"""HEAD-check definition_url_oxford / definition_url_cambridge in data/oald.

Usage:
  python scripts/verify_definition_urls.py
  python scripts/verify_definition_urls.py --workers 24
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "oald"
JSON_PATH = OUT / "words.json"
REPORT_PATH = OUT / "definition_url_check.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def url_ok(url: str, timeout: float = 20.0) -> tuple[bool, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # Prefer GET with Range — some CDNs reject HEAD
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={**headers, "Referer": url.rsplit("/", 1)[0] + "/"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            if code in (200, 206, 301, 302, 303, 307, 308):
                return True, str(code)
            return False, str(code)
    except urllib.error.HTTPError as e:
        if e.code in (403, 405, 501):
            try:
                req2 = urllib.request.Request(
                    url,
                    headers={**headers, "Range": "bytes=0-0"},
                )
                with urllib.request.urlopen(req2, timeout=timeout) as resp:
                    return resp.status in (200, 206), f"GET-range {resp.status}"
            except urllib.error.HTTPError as e2:
                return False, f"HTTP {e2.code}"
            except Exception as e2:  # noqa: BLE001
                return False, str(e2)[:80]
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:80]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    fields = ("definition_url_oxford", "definition_url_cambridge")
    urls: dict[str, set[str]] = {f: set() for f in fields}
    empty = {f: 0 for f in fields}
    for r in rows:
        for f in fields:
            u = (r.get(f) or "").strip()
            if not u:
                empty[f] += 1
            else:
                urls[f].add(u)

    all_urls = sorted(set().union(*urls.values()))
    print(f"entries={len(rows)}")
    for f in fields:
        print(f"  {f}: unique={len(urls[f])} empty={empty[f]}")
    print(f"total unique urls={len(all_urls)}", flush=True)

    alive: dict[str, tuple[bool, str]] = {}
    lock = Lock()
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(url_ok, u): u for u in all_urls}
        for fut in as_completed(futs):
            u = futs[fut]
            ok, detail = fut.result()
            with lock:
                alive[u] = (ok, detail)
                done += 1
                if done % 500 == 0 or done == len(all_urls):
                    dead_n = sum(1 for ok, _ in alive.values() if not ok)
                    print(
                        f"checked {done}/{len(all_urls)} dead={dead_n} "
                        f"({time.time() - t0:.0f}s)",
                        flush=True,
                    )

    dead_urls = sorted(u for u, (ok, _) in alive.items() if not ok)
    by_field_dead = {f: [] for f in fields}
    entries_dead: list[dict] = []

    for r in rows:
        bad_fields = []
        for f in fields:
            u = (r.get(f) or "").strip()
            if not u:
                bad_fields.append({"field": f, "url": "", "reason": "empty"})
            elif not alive.get(u, (True, ""))[0]:
                bad_fields.append(
                    {
                        "field": f,
                        "url": u,
                        "reason": alive[u][1],
                    }
                )
                by_field_dead[f].append(u)
        if bad_fields:
            entries_dead.append(
                {
                    "word": r.get("word_gb"),
                    "pos": r.get("lexical_category"),
                    "problems": bad_fields,
                }
            )

    report = {
        "entries": len(rows),
        "unique_urls": len(all_urls),
        "alive": len(all_urls) - len(dead_urls),
        "dead": len(dead_urls),
        "empty_by_field": empty,
        "dead_by_field": {f: len(set(by_field_dead[f])) for f in fields},
        "entries_with_dead_or_empty": len(entries_dead),
        "dead_urls": [
            {"url": u, "detail": alive[u][1]} for u in dead_urls
        ],
        "entry_samples": entries_dead[:40],
        "elapsed_sec": round(time.time() - t0, 1),
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print()
    print(f"DEAD urls: {len(dead_urls)}")
    print(f"entries with problems: {len(entries_dead)}")
    for f in fields:
        print(f"  {f} dead unique: {report['dead_by_field'][f]}")
    for item in report["dead_urls"][:30]:
        print(f"  [{item['detail']}] {item['url']}")
    if len(dead_urls) > 30:
        print(f"  … +{len(dead_urls) - 30} more")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
