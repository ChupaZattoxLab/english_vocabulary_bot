"""Build a full words JSON for the Android fact-check app."""
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
        word_us = entry.get("word_us") or ""
        word_gb = entry.get("word_gb") or ""
        slim.append(
            {
                "id": i,
                "word": word_us or word_gb,
                "wordUs": word_us,
                "wordGb": word_gb,
                "pos": entry.get("lexical_category") or "",
                "cefr": entry.get("cefr") or "",
                "definitionUrlOxford": entry.get("definition_url_oxford") or "",
                "definitionUrlCambridge": entry.get("definition_url_cambridge") or "",
                "ipaUs": list(entry.get("ipa_us") or []),
                "ipaGb": list(entry.get("ipa_gb") or []),
                "definition": entry.get("definition") or "",
                "example": entry.get("example") or "",
                "extraSenses": [],
                "audioUs": list(entry.get("audio_source_us") or []),
                "audioGb": list(entry.get("audio_source_gb") or []),
                "main": tr.get("main") or "",
                "also": list(tr.get("also") or []),
                "status": "PENDING",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(slim, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"Wrote {len(slim)} entries to {OUT} ({size_mb:.2f} MB)")
    print("sample keys:", list(slim[0].keys()))


if __name__ == "__main__":
    main()
