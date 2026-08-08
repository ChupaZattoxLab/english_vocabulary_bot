"""Safe, reloadable HTML card template rendering."""

from __future__ import annotations

import html
import string
from collections.abc import Mapping
from pathlib import Path

from tgbot.constants import TELEGRAM_MESSAGE_MAX_LEN

ALLOWED_FIELDS = {
    "word",
    "word_upper",
    "word_us",
    "word_us_upper",
    "word_gb",
    "word_gb_upper",
    "lexical_category",
    "cefr",
    "definition",
    "ipa",
    "ipa_us",
    "ipa_gb",
    "example",
    "translation",
    "dialect",
    "dialect_flag",
    "heading_definition",
    "heading_example",
    "heading_translation",
    "flag_us",
    "flag_gb",
}
REQUIRED_FIELDS = {
    "lexical_category",
    "cefr",
    "definition",
    "example",
    "translation",
}


class CardTemplateError(ValueError):
    """Raised when a card template is missing or unsafe."""


class CardTemplate:
    def __init__(self, path: Path):
        self.path = path
        self._mtime_ns = -1
        self._template = ""
        self._load_if_changed()

    def _load_if_changed(self) -> None:
        try:
            stat = self.path.stat()
        except OSError as exc:
            raise CardTemplateError(
                f"could not read card template {self.path}: {exc}"
            ) from exc
        if stat.st_mtime_ns == self._mtime_ns:
            return
        template = self.path.read_text(encoding="utf-8").strip()
        if not template:
            raise CardTemplateError("card template must not be empty")

        fields: set[str] = set()
        try:
            parts = string.Formatter().parse(template)
            for _, field_name, format_spec, conversion in parts:
                if field_name is None:
                    continue
                if field_name not in ALLOWED_FIELDS:
                    raise CardTemplateError(
                        f"unsupported card template field {field_name!r}"
                    )
                if format_spec or conversion:
                    raise CardTemplateError(
                        "format specifications and conversions are not allowed"
                    )
                fields.add(field_name)
        except ValueError as exc:
            raise CardTemplateError(f"invalid card template: {exc}") from exc
        missing = sorted(REQUIRED_FIELDS - fields)
        if missing:
            raise CardTemplateError(
                f"card template is missing required fields: {', '.join(missing)}"
            )
        if not fields.intersection(
            {
                "word",
                "word_upper",
                "word_us",
                "word_us_upper",
                "word_gb",
                "word_gb_upper",
            }
        ):
            raise CardTemplateError(
                "card template must contain at least one word field"
            )
        if "ipa" not in fields and not {"ipa_us", "ipa_gb"}.issubset(fields):
            raise CardTemplateError(
                "card template must contain {ipa}, or both {ipa_us} and {ipa_gb}"
            )
        self._template = template
        self._mtime_ns = stat.st_mtime_ns

    def render(self, values: Mapping[str, str]) -> str:
        self._load_if_changed()
        escaped = {
            field: html.escape(str(values.get(field, "")), quote=False)
            for field in ALLOWED_FIELDS
        }
        rendered = self._template.format_map(escaped)
        if len(rendered) > TELEGRAM_MESSAGE_MAX_LEN:
            raise CardTemplateError(
                "rendered card exceeds Telegram's "
                f"{TELEGRAM_MESSAGE_MAX_LEN}-character text limit"
            )
        return rendered

    def reload(self) -> None:
        """Validate and reload the template even when its timestamp is unchanged."""
        self._mtime_ns = -1
        self._load_if_changed()
