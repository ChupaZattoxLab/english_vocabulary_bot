"""Build a slim words JSON for the Android fact-check app."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "words.json"
OUT = ROOT / "android-app" / "app" / "src" / "main" / "assets" / "words_slim.json"


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    slim = []
    for i, entry in enumerate(data):
        tr = (entry.get("translations") or {}).get("ru") or {}
        slim.append(
            {
                "id": i,
                "word": entry.get("word_us") or entry.get("word_gb") or "",
                "pos": entry.get("lexical_category") or "",
                "main": tr.get("main") or "",
                "also": list(tr.get("also") or []),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(slim, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"Wrote {len(slim)} entries to {OUT} ({size_mb:.2f} MB)")
    print("sample:", slim[0])


if __name__ == "__main__":
    main()
